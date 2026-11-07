import copy
import json
import tempfile
import unittest
from types import SimpleNamespace

from decision_lab import api_lab as al, collection as co, inquiry_framing as f


def record(manifest, choose, *, partial=None, synthetic=True):
    entries = al.synthetic_entries(manifest)
    for request, entry in zip(manifest['requests'], entries):
        action = choose(request)
        answer = entry['response']['answers'][0]
        answer.update(choice=action, confidence=1.0)
        for p in answer['probabilities']:
            p['probability'] = float(p['value'] == action)
        entry['response']['usage'] = {'input_tokens': 10, 'input_tokens_details': {'cached_tokens': 2}, 'output_tokens': 0}
    if partial is not None:
        entries = entries[:partial]
    return al.build_record(manifest, entries, provenance='synthetic' if synthetic else 'imported', allow_partial=True)


class InquiryFramingTests(unittest.TestCase):
    def setUp(self):
        self.design = f.build_design()
        self.workflow = f.start(self.design)
        self.manifest = f.prepare_round(self.workflow)

    def test_factorial_inputs_isolate_warning_and_hidden_worlds(self):
        self.assertEqual(len(self.manifest['requests']), 128)
        groups = {}
        for r in self.manifest['requests']:
            plan = next(p for p in self.workflow['planned'] if p['id'] == r['trial']['unit_id'])
            body = copy.deepcopy(r['body']);v = json.loads(body['input'])
            self.assertEqual(set(v), {'rule', 'initial_dossier', 'query_contract', 'losses'})
            if plan['cell'].endswith('warning'):
                self.assertIs(v['initial_dossier'].pop('provisional'), True)
                self.assertEqual(v['initial_dossier'].pop('notice'), f.NOTICE)
            self.assertEqual(set(v['initial_dossier']), {'claim', 'source_text'})
            body['input'] = v
            key = (plan['item_id'], plan['world_id'], plan['cell'].split('_')[0], plan['replicate'])
            groups.setdefault(key, []).append(body)
        for bodies in groups.values():
            self.assertEqual(len(bodies), 2)
            self.assertEqual(bodies[0], bodies[1])
        for item in self.design['items']:
            for rep in range(2):
                self.assertEqual(groups[(item['id'], 'a', 'missing', rep)], groups[(item['id'], 'b', 'missing', rep)])
                self.assertNotEqual(groups[(item['id'], 'a', 'sufficient', rep)], groups[(item['id'], 'b', 'sufficient', rep)])
        self.assertEqual(sum(i['preliminary_claim'] == '初步建议：允许。' for i in self.design['items']), 4)

    def test_design_and_planned_tampering_rejected_even_if_resealed(self):
        d = copy.deepcopy(self.design);d['items'][0]['worlds'][0]['gold'] = 'commit:hold'
        with self.assertRaises(al.ApiLabError):f.start(d)
        d = copy.deepcopy(self.design);d['losses']['query'] = True
        with self.assertRaises(al.ApiLabError):f.start(d)
        w = copy.deepcopy(self.workflow);w['planned'][0]['world_id'] = 'b';f._seal(w)
        with self.assertRaises(al.ApiLabError):f.report(w)

    def test_controls_have_complete_denominators_and_known_effects(self):
        expected = {'oracle': (64, 128, 0, 64, 192), 'always-query': (128, 128, 0, 128, 256),
                    'stop': (0, 64, 64, 192, 128)}
        for policy, (queries, correct, abstained, loss, requests) in expected.items():
            w = f.demo(self.design, policy=policy);r = f.report(w);s = r['summary']
            self.assertEqual((s['planned'], s['completed'], s['missing']), (128, 128, 0))
            self.assertEqual((s['query_count'], s['correct_commit'], s['abstained'], s['total_loss']),
                             (queries, correct, abstained, loss))
            self.assertEqual(r['native']['request_count'], requests)
            self.assertIsNone(r['native']['call_count']);self.assertIsNone(r['native']['usage'])
            self.assertTrue(r['synthetic']);self.assertIsNone(f.prepare_round(w))
            self.assertEqual(r['effects']['interaction']['query_rate_difference'], 0)
        r = f.report(f.demo(self.design))
        self.assertEqual(r['effects']['missing_minus_sufficient_neutral']['query_rate_difference'], 1)

    def test_known_interaction_sign_and_pair_unit(self):
        def choose(r):
            c = r['trial']['condition']
            return 'query:record' if c.startswith('sufficient_warning') else 'abstain'
        w = f.apply_round(self.workflow, record(self.manifest, choose));r = f.report(w)
        self.assertEqual(r['effects']['warning_sufficient']['query_rate_difference'], 1)
        self.assertEqual(r['effects']['warning_missing']['query_rate_difference'], 0)
        self.assertEqual(r['effects']['interaction']['query_rate_difference'], -1)
        self.assertEqual(r['effects']['interaction']['planned_pairs'], 32)
        for family in r['families'].values():
            self.assertEqual(family['effects']['interaction']['query_rate_difference'], -1)
            self.assertEqual(family['effects']['interaction']['planned_pairs'], 4)

    def test_followup_only_for_actual_query_and_reveals_original_record(self):
        def choose(r):return 'query:record' if r['trial']['condition'].startswith('missing_neutral') else 'abstain'
        w = f.apply_round(self.workflow, record(self.manifest, choose));m = f.prepare_round(w)
        self.assertEqual(len(m['requests']), 32)
        for request in m['requests']:
            v = json.loads(request['body']['input'])
            self.assertEqual(v['previous_action'], 'query:record')
            plan = next(p for p in w['planned'] if p['id'] == request['trial']['unit_id'])
            _, world = f._task(w, plan)
            self.assertEqual(v['revealed_record'], world['record'])
            self.assertNotIn('query:record', [c['value'] for c in request['body']['questions'][0]['choices']])
            self.assertNotIn('gold', v);self.assertNotIn('world_id', v)
        with self.assertRaises(al.ApiLabError):f.apply_round(w, record(self.manifest, choose))

    def test_partial_native_record_remains_pending_and_can_complete(self):
        partial = record(self.manifest, lambda r: 'abstain', partial=1)
        w = f.apply_round(self.workflow, partial);r = f.report(w)
        self.assertEqual((r['summary']['first_observed'], r['summary']['missing']), (1, 127))
        self.assertIsNone(r['summary']['first_query_rate']);self.assertIsNone(r['summary']['total_loss'])
        self.assertIsNone(r['effects']['interaction']['query_rate_difference'])
        self.assertTrue(r['pending_round'])
        with self.assertRaises(al.ApiLabError):f.prepare_round(w)
        full = record(self.manifest, lambda r: 'abstain')
        w = f.apply_round(w, full)
        self.assertEqual(f.report(w)['summary']['completed'], 128)
        self.assertIsNone(f.prepare_round(w))
        changed = record(self.manifest, lambda r: 'query:record')
        with self.assertRaises(al.ApiLabError):f.apply_round(f.apply_round(self.workflow, partial), changed)

    def test_api_failure_is_not_business_abstain_or_no_query(self):
        source = record(self.manifest, lambda r: 'abstain')
        source['responses'][0] = {'request_id': self.manifest['requests'][0]['id'], 'http_status': 503,
                                  'error': 'http_error', 'response': {'error': {'message': 'fixture'}}}
        f._seal(source)
        r = f.report(f.apply_round(self.workflow, source))
        self.assertEqual((r['summary']['completed'], r['summary']['api_failed'], r['summary']['abstained']), (128, 1, 127))
        self.assertEqual(r['summary']['total_loss'], 12 + 3 * 127)
        self.assertIsNone(r['cells']['sufficient_neutral']['first_query_rate'])
        self.assertIsNone(r['effects']['warning_sufficient']['query_rate_difference'])
        self.assertEqual(r['effects']['warning_missing']['query_rate_difference'], 0)
        self.assertIsNone(r['episodes'][0]['correct'])

    def test_unknown_and_refusal_preserved(self):
        source = record(self.manifest, lambda r: 'unknown')
        r = f.report(f.apply_round(self.workflow, source))
        self.assertEqual(r['summary']['api_failed'], 128)
        self.assertEqual(r['summary']['first_statuses'], {'unknown': 128})
        self.assertEqual(r['summary']['total_loss'], 1536)
        self.assertIsNone(r['summary']['first_query_rate'])
        source = record(self.manifest, lambda r: 'abstain')
        for e in source['responses']:
            e['response']['answers'][0] = {'name': 'action', 'type': 'refusal', 'refusal': 'fixture'}
        f._seal(source)
        # Native normalizer owns exact refusal representation; framing preserves it.
        self.assertEqual(f.report(f.apply_round(self.workflow, source))['summary']['first_statuses'], {'refusal': 128})

    def test_missing_answer_is_pending_and_imported_nested_usage_is_retained(self):
        source = record(self.manifest, lambda r: 'abstain', synthetic=False)
        r = f.report(f.apply_round(self.workflow, source))
        self.assertIsNone(r['synthetic']);self.assertIsNone(r['native']['cost'])
        self.assertEqual(r['native']['usage'], {'input_tokens': 1280, 'input_tokens_details': {'cached_tokens': 256}, 'output_tokens': 0})
        source['responses'][0]['response']['answers'] = [];f._seal(source)
        r = f.report(f.apply_round(self.workflow, source))
        self.assertTrue(r['pending_round']);self.assertEqual(r['summary']['missing'], 1)
        self.assertIsNone(r['effects']['interaction']['query_rate_difference'])

    def test_received_source_manifest_and_bytes_are_bound(self):
        class Http:
            calls = 0
            def post_json(_, endpoint, headers, body):
                _.calls += 1
                e = record(self.manifest, lambda r: 'abstain')['responses'][0]['response']
                return SimpleNamespace(status=200, body=json.dumps(e).encode())
        with tempfile.TemporaryDirectory() as temp:
            http = Http()
            data = co.collect(co.api_plan(self.manifest), temp + '/collection', allow_network=True, max_calls=128, max_questions=128,
                              max_estimated_tokens=1_000_000, credential='fixture', client=http, cancel=lambda: http.calls == 2)
            self.assertEqual(len(data['attempts']), 2)
            w = f.apply_round(self.workflow, data);r = f.report(w)
            self.assertEqual(r['native']['call_count'], 2)
            self.assertEqual(r['native']['usage']['input_tokens'], 20)
            self.assertEqual(r['summary']['missing'], 126)
            corrupt = copy.deepcopy(data);corrupt['attempts'][0]['parsed']['model'] = 'changed';f._seal(corrupt)
            with self.assertRaises(al.ApiLabError):f.apply_round(self.workflow, corrupt)
            uncertain = copy.deepcopy(data);uncertain['attempts'][-1]['delivery'] = 'uncertain';f._seal(uncertain)
            r = f.report(f.apply_round(self.workflow, uncertain))
            self.assertEqual(r['summary']['first_statuses']['uncertain'], 1)
            self.assertEqual(r['native']['call_count'], 2)
            self.assertIsNone(r['summary']['first_query_rate'])

    def test_complete_source_does_not_mutate_input_and_false_digest_rejected(self):
        source = record(self.manifest, lambda r: 'abstain')
        before = copy.deepcopy((self.workflow, source))
        w = f.apply_round(self.workflow, source)
        self.assertEqual((self.workflow, source), before)
        w['model'] = 'other'
        with self.assertRaises(al.ApiLabError):f.report(w)


if __name__ == '__main__':
    unittest.main()
