"""Explicit measurement and native-task projections; no provider calls."""
from __future__ import annotations

import copy

from . import api_lab as al


def definition(request, qid):
    grade = request['rubric']['questions'][qid]
    if request['experiment'] == 'decision-roles':
        return {'id': 'role_workflow_loss', 'unit': 'task_loss',
                'semantics': 'retained role loss matrix'}
    if 'numeric_truth' in grade or grade['kind'] == 'number':
        return {'id': 'absolute_error', 'unit': grade.get('unit', 'probability' if 'numeric_truth' in grade else 'score_index'),
                'semantics': 'absolute distance from retained numeric gold'}
    return {'id': 'classification_error', 'unit': 'error', 'semantics': 'zero for acceptable answer, one for incorrect answer'}


def attach(row, request, qid, route):
    measure = definition(request, qid)
    if measure['id'] == 'absolute_error' and row['outcome'] == 'ok':
        grade = request['rubric']['questions'][qid]
        gold = grade.get('numeric_truth', grade.get('expected'))
        value = float(row['value'])  # Explicit numeric rubric permits numeric Choice labels.
        al.require(al.finite(value) and al.finite(gold), 'numeric measurement needs finite value and gold')
        row['loss'] = abs(value - gold)
    row['measurement'] = {**measure, 'value': row['loss'] if row['outcome'] == 'ok' else None}
    question = al.native_questions(request['body'], route)[qid]
    kind = question['type']
    # These parsers require the provider's explicit confidence field. Neither
    # correctness probability nor a max-mass formula is inferred from that name.
    row['selection_signal'] = {'id': f'{route}:{kind}:native_confidence',
                               'semantics': 'provider-reported confidence; formula not asserted by this projection',
                               'formula_known': False, 'value': row.get('confidence')}
    if kind in ('predicate', 'noul'):
        row['selection_signal']['id'] = f'{route}:{kind}:no_independent_confidence'
        row['selection_signal']['semantics'] = 'event probability is the answer; no independent confidence signal'


def task_contract(request, route):
    """Conservatively equate only the documented native spelling differences."""
    body = request['body']
    questions = []
    for qid, q in al.native_questions(body, route).items():
        kind = q['type']
        item = {'id': qid, 'type': 'predicate' if kind == 'noul' else kind,
                'instructions': q['instructions']}
        if kind == 'choice':
            item['choices'] = ([{'value': c['value'], 'description': c.get('description', '')} for c in q['choices']]
                               if route == 'decisions' else
                               [{'value': v, 'description': d} for v, d in q['criteria'].items()])
        elif kind == 'score':
            item['levels'] = ([level.get('description') or level['label'] for level in q['levels']]
                              if route == 'decisions' else q['criteria'])
        questions.append(item)
    return copy.deepcopy({'experiment': request['experiment'],
                          'input': body.get('input') if route == 'decisions' else body.get('state'),
                          'questions': questions, 'assets': body.get('assets', {}),
                          'required_headers': request['required_headers'],
                          'rubric': request['rubric'],
                          'measurements': {qid: definition(request, qid) for qid in al.native_questions(body, route)}})
