"""Offline arithmetic for Decision Models and APIs research, 2026-10-08 UTC.

No network calls, API credentials, or measured provider accuracy/latency.
Prices are documentation snapshots. Scenarios assume equal BILLABLE token
counts, not equal original text. Use actual token usage for deployment estimates.
"""
from decimal import Decimal as D
from pathlib import Path
import json
import math

def input_cost(requests, billed_input_tokens, price_per_million):
    return D(str(requests)) * D(str(billed_input_tokens)) * D(str(price_per_million)) / D(1000000)

def generated_cost(requests, billed_input_tokens, output_tokens, input_price, output_price, multiplier=1):
    return (input_cost(requests, billed_input_tokens, input_price) + input_cost(requests, output_tokens, output_price)) * D(str(multiplier))

def validate_distribution(values):
    p = tuple(D(str(v)) for v in values)
    if len(p) < 2 or any(x < 0 or x > 1 for x in p) or abs(sum(p)-1) > D('0.000001'):
        raise ValueError('Expected at least two non-negative probabilities summing to one')
    return p

def choice_confidence(values):
    p = validate_distribution(values)
    uniform = 1 / D(len(p))
    return (max(p)-uniform)/(1-uniform)

def score_confidence(values):
    p = validate_distribution(values)
    mode = max(range(len(p)), key=p.__getitem__)
    middle = D(len(p)-1)/2
    uniform_spread = sum(abs(D(k)-middle) for k in range(len(p)))/D(len(p))
    actual_spread = sum(x*abs(k-mode) for k,x in enumerate(p))
    return max(D(0),1-actual_spread/uniform_spread)

def expectation(values):
    return sum(D(k)*p for k,p in enumerate(validate_distribution(values)))

def normalized_entropy_confidence(values):
    p = validate_distribution(values)
    entropy = -sum(float(x)*math.log(float(x)) for x in p if x)
    return 1-entropy/math.log(len(p))

def build_results():
    prices = [
        ('Jev / TypeSafe native','0.042'),
        ('Clef-flash / Cloudflare native','0.09'),
        ('Clef / Cloudflare native','0.24'),
        ('GPT-6 Luna Decisions / OpenAI native','0.10'),
        ('Liquid d1 / Vercel route','0.04'),
        ('Clef-flash / OpenRouter Prime Intellect route','0.021'),
        ('Clef / OpenRouter Prime Intellect route','0.042'),
        ('GLiDE / Fastino native','0.15'),
        ('GLiNER-2.5-Decide / Fastino native','0.03'),
        ('span-01 Pro / Respan native','0.02'),
        ('Aplomb 1 / EmpirioLabs native','0.02'),
        ('Decider V1.1 27B / OpenRouter route','0.02'),
        ('Solar Decide / OpenRouter promotional route','0.05')
    ]
    workload = dict(requests=1000000,billed_input_tokens_per_request=1000,
                    assumptions=['Same billed token counts across routes, not matched text.','No images, retries, fees, discounts, regional/long-context premium, minimum charges or taxes.','One request is not necessarily one question.','No accuracy or latency equivalence assumed.'])
    list_costs=[{'route':name,'usd_per_million_input_tokens':float(D(price)),'usd_per_million_requests':float(input_cost(1000000,1000,price))} for name,price in prices]
    direct = generated_cost(1000000,1000,8,'0.10','0.50')
    gate = input_cost(1000000,1000,'0.042')
    native = input_cost(1000000,1000,'0.10')
    cascade=[]
    for escalated in ['0','0.25','0.5','0.75','1']:
        total=gate+D(escalated)*direct
        cascade.append({'escalated_fraction':float(D(escalated)),'total_usd':float(total),'saving_fraction':float(1-total/direct)})
    scenarios={
        'baseline':'GPT-6 Luna Responses Standard, 1000 billed input + 8 output tokens; reasoning none; no cache',
        'direct_usd':float(direct),'native_decisions_usd':float(native),
        'native_decisions_input_only_saving_fraction':float(1-native/direct),
        'responses_batch_usd':float(direct/2),
        'batch_note':'Responses Batch is asynchronous and has its own availability/SLA; do not apply discount to Decisions.',
        'jev_screen_usd':float(gate),'break_even_max_escalation_fraction':float(1-gate/direct),
        'cascade':cascade,'scope':'Arithmetic only; no model quality, calibration, input overhead or live bills measured.'}
    distributions=[[0,1,0],[0.5,0,0.5],[0.6,0.3,0.1],[0.7,0.1,0.1,0.1]]
    demos=[{'probabilities':p,'score_expectation':float(expectation(p)),
            'jev_choice_confidence':float(choice_confidence(p)),
            'jev_score_confidence':float(score_confidence(p)),
            'telnyx_normalized_entropy_confidence':normalized_entropy_confidence(p),
            'clef_hf_helper_max_probability':float(max(p))} for p in distributions]
    multiplicity={'state_tokens':8000,'tokens_per_question':400,'questions':10,
        'shared_state_once_billed_tokens':12000,'state_repeated_per_question_billed_tokens':84000,
        'repeated_over_shared_ratio':7,'illustrative_input_usd_per_million':0.05,
        'shared_usd':0.0006,'repeated_usd':0.0042,
        'scope':'Counterfactual equal-price arithmetic; illustrates billing multiplicity, not measured tokenizer counts or quality. Levanto documentation uses the repeated 84000-token example.'}
    return {'as_of_utc':'2026-10-08','workload':workload,'quoted_price_arithmetic':list_costs,
            'short_answer_and_cascade_scenarios':scenarios,'probability_formula_examples':demos,
            'billing_multiplicity_scenario':multiplicity,
            'confidence_scope':'Jev and Telnyx documented formulas vs pinned Clef HF helper; not an assertion about hosted Clef confidence. Formula demonstrations do not establish calibration.',
            'confidence_sources':['https://docs.typesafe.ai/confidence','https://developers.telnyx.com/docs/inference/decision-models','https://huggingface.co/Cloudflare/clef-flash/blob/41318bf2106d135c7a92da745fec4b255279b4de/joint_schema_model.py']}

if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,default=Path(__file__).with_name('calculations.json'))
    args=parser.parse_args()
    result=build_results()
    # Independent known arithmetic checks for the report's material quantities.
    assert input_cost(1000000,1000,'0.042') == D('42')
    assert generated_cost(1000000,1000,8,'0.10','0.50') == D('104')
    assert abs(choice_confidence([.6,.3,.1])-D('.4')) < D('0.0000001')
    assert expectation([0,1,0]) == expectation([.5,0,.5]) == 1
    assert score_confidence([.5,0,.5]) == 0
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'output':str(args.out),'price_scenarios':len(result['quoted_price_arithmetic']),
                      'direct_usd':104,'jev_half_escalated_usd':94,'arithmetic_checks':'passed'},ensure_ascii=False))
