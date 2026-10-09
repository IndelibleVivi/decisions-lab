"""Offline audit of public sys1-eval response records; no API/network/model calls.

Inputs are exact fields projected from the author's immutable Git blobs.
Gold and stable IDs come from cases-large-flip.jsonl. The reversal builder
preserves gold/IDs. This file independently recomputes counts without importing
the author's analysis. The A routing flip also drops a difficulty question:
see protocol_caveat, so interpret B/F changes as the cleaner order test.
"""
from __future__ import annotations
from pathlib import Path
from collections import Counter
import hashlib
import json
import math

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / 'sys1_order_inputs.jsonl'
EXPECTED = ROOT / 'author_numbers.json'

def wilson(k, n, z=1.96):
    if not n:
        return None
    p = k / n
    divisor = 1 + z*z/n
    center = p + z*z/(2*n)
    delta = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n))
    return [(center-delta)/divisor, (center+delta)/divisor]

def valid(row):
    return bool(row and row['ok'] and row['answer'] and row['answer'].get('type') == 'choice')

def confidence(row):
    p = row['answer'].get('probabilities') or {}
    if not p:
        raise ValueError('Missing option probabilities; no provider-confidence fallback is allowed')
    return max(p.values())

def summarize(rows):
    result = {'cases':len(rows),'gold_distribution':dict(Counter(r['gold'] for r in rows))}
    for model in ('jev','laya'):
        original = [(r, r['models'][model+'_original']) for r in rows if valid(r['models'][model+'_original'])]
        reversed_ = [(r, r['models'][model+'_reversed']) for r in rows if valid(r['models'][model+'_reversed'])]
        paired = [r for r in rows if valid(r['models'][model+'_original']) and valid(r['models'][model+'_reversed'])]
        high = [(r,p) for r,p in original if confidence(p) is not None and confidence(p)>=0.9]
        correct = sum(p['answer']['choice'] == r['gold'] for r,p in original)
        reverse_correct = sum(p['answer']['choice'] == r['gold'] for r,p in reversed_)
        changed = sum(r['models'][model+'_original']['answer']['choice'] != r['models'][model+'_reversed']['answer']['choice'] for r in paired)
        high_wrong = sum(p['answer']['choice'] != r['gold'] for r,p in high)
        result[model] = {
            'original_answered':len(original), 'original_correct':correct,
            'original_accuracy':correct/len(original) if original else None,
            'original_accuracy_wilson95':wilson(correct,len(original)),
            'original_predictions':dict(Counter(p['answer']['choice'] for r,p in original)),
            'reversed_answered':len(reversed_), 'reversed_correct':reverse_correct,
            'reversed_accuracy':reverse_correct/len(reversed_) if reversed_ else None,
            'paired':len(paired),'prediction_changed':changed,
            'prediction_change_fraction':changed/len(paired) if paired else None,
            'high_confidence_definition':'max(option probabilities) >= 0.9',
            'high_confidence_n':len(high),'high_confidence_errors':high_wrong,
            'high_confidence_error_fraction':high_wrong/len(high) if high else None,
        }
    return result

rows = [json.loads(line) for line in INPUT.read_text().splitlines() if line.strip()]
if len({r['id'] for r in rows}) != len(rows):
    raise ValueError('Duplicate case IDs in evidence projection')
probability_records_checked = 0
max_distribution_sum_deviation = 0.0
for case in rows:
    expected_models = {'jev_original', 'laya_original', 'jev_reversed', 'laya_reversed'}
    if set(case['models']) != expected_models:
        raise ValueError(f"Unexpected model variants for {case['id']}")
    expected_candidates = case['candidate_count']
    if expected_candidates is None and case['track'] == 'A_model_router':
        expected_candidates = 2  # Confirmed by the original route construction.
    for variant, record in case['models'].items():
        if not valid(record):
            raise ValueError(f"Invalid saved answer: {case['id']} / {variant}")
        probabilities = record['answer'].get('probabilities') or {}
        if len(probabilities) != expected_candidates:
            raise ValueError(f"Candidate-count mismatch: {case['id']} / {variant}")
        if any(not isinstance(p, (int, float)) or not math.isfinite(p) or not 0 <= p <= 1
               for p in probabilities.values()):
            raise ValueError(f"Invalid option probability: {case['id']} / {variant}")
        if record['answer']['choice'] not in probabilities or case['gold'] not in probabilities:
            raise ValueError(f"Choice or gold missing from options: {case['id']} / {variant}")
        max_distribution_sum_deviation = max(max_distribution_sum_deviation,
                                             abs(sum(probabilities.values())-1.0))
        probability_records_checked += 1
# Preserve source rounding, including sums near 0.99; do not renormalize maxP.
tracks = sorted({r['track'] for r in rows})
computed = {t:summarize([r for r in rows if r['track']==t]) for t in tracks}
computed['ALL'] = summarize(rows)
expected = json.loads(EXPECTED.read_text())
matches=[]
for t in tracks:
    for model, field in (('laya','acc_a'),('jev','acc_b')):
        actual=computed[t][model]['original_accuracy']
        stated=expected['main'][t][field]
        matches.append({'track':t,'model':model,'metric':'original_accuracy','computed':actual,'author':stated,'matches':abs(actual-stated)<1e-8})
for t in tracks+['ALL']:
    for model in ('jev','laya'):
        actual=computed[t][model]['prediction_change_fraction']
        stated=expected['order_flip'][model][t][0]
        matches.append({'track':t,'model':model,'metric':'answer_change_fraction','computed':actual,'author':stated,'matches':abs(actual-stated)<1e-8})

report={
    'as_of':'2026-10-08',
    'scope':'Independent arithmetic reanalysis of author-released historical response records; no current inference or API call.',
    'input_sha256':hashlib.sha256(INPUT.read_bytes()).hexdigest(),
    'input_rows':len(rows),'results':computed,'author_summary_checks':matches,
    'option_probability_records_checked':probability_records_checked,
    'probability_validation':'All four variants per case: finite [0,1] values, complete candidate count, choice/gold present. Original rounding retained; no renormalization.',
    'max_distribution_sum_deviation':max_distribution_sum_deviation,
    'provider_confidence_fallback_used':False,
    'all_author_summary_checks_match':all(x['matches'] for x in matches),
    'protocol_caveat':'The original A_model_router requests include route and difficulty, while build_flip_large.mjs retains only choice questions. Thus A/ALL change rates are not solely attributable to answer-order reversal. B_tool_selection and F_cardinality_multilingual have only the choice question and provide the cleaner order comparison.',
    'generalization_limit':'RouterBench labels use historical cheap/strong outcomes, generic model descriptions and clipped request text. These counts cannot establish that current decision models universally fail routing. Other tracks use public historical benchmarks, not current production requests.',
    'interval_note':'Wilson intervals are descriptive binomial intervals for each selected subset; selection, clusters and correlated variants prevent treating them as population or production guarantees.',
}
OUT=ROOT/'sys1_reanalysis.json'
OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'report':str(OUT),'rows':len(rows),'checks_match':report['all_author_summary_checks_match'],'compact':{t:{m:{k:v for k,v in computed[t][m].items() if k in ('original_correct','original_answered','original_accuracy','prediction_changed','paired','prediction_change_fraction','high_confidence_n','high_confidence_errors')} for m in ('jev','laya')} for t in tracks+['ALL']}},ensure_ascii=False,indent=2))
