"""Scientific measurement/identity regression checks; no provider calls."""
import copy
import json
import unittest

from decision_lab import api_lab as al, collection, comparison as c, ledger


def manifest(route='decisions', *, gold=.4, unit='probability', text='Estimate event A.', replicates=1):
    row = {'id': 'event', 'experiment': 'measurement-test', 'input': text,
           'trial': {'unit_id': 'world', 'source_family': 'family', 'condition': 'base', 'split': 'test'},
           'questions': [{'id': 'q', 'type': 'predicate', 'instructions': 'Probability of A?'}],
           'rubric': {'questions': {'q': {'kind': 'boolean', 'expected': False,
                                        'numeric_truth': gold, 'unit': unit}}}}
    return al.prepare_payload(al.Suite({}, [row]), [row], route=route, replicates=replicates, account_id="a" * 32)


def view(m, value=.5):
    entries = al.oracle_entries(m)
    for entry in entries:
        answers = al.answer_envelope(entry['response'], m['route'])['answers']
        answer = answers[0] if m['route'] == 'decisions' else answers['q']
        answer['probability' if m['route'] == 'decisions' else 'noul'] = value
    return ledger.from_api(m, entries, metadata={'provenance': 'synthetic', 'synthetic': True})


class MeasurementTests(unittest.TestCase):
    def test_numeric_error_is_continuous_not_correctness(self):
        m = manifest()
        near, far = view(m, .5), view(m, 0)
        self.assertAlmostEqual(near['trials'][0]['loss'], .1)
        self.assertAlmostEqual(far['trials'][0]['loss'], .4)
        self.assertEqual(near['trials'][0]['measurement']['id'], 'absolute_error')
        self.assertEqual(near['trials'][0]['measurement']['unit'], 'probability')
        self.assertAlmostEqual(c.compare_runs(near, far)['estimate']['delta'], .3)
        # Same answer .5, distinct retained golds .4 and .0 => .1 and .5.
        self.assertEqual(view(manifest(gold=0), .5)['trials'][0]['loss'], .5)

    def test_explicit_cross_route_pairing_keeps_native_identity_and_evidence(self):
        left, right = view(manifest()), view(manifest('clef'))
        with self.assertRaisesRegex(c.ComparisonError, 'dataset_id'):
            c.compare_runs(left, right)
        spec = c.make_pairing_spec(left, right)
        spec = json.loads(json.dumps(spec))
        result = c.compare_runs(left, right, pairing=spec, bootstrap_samples=200)
        self.assertEqual(result['estimate']['delta'], 0)
        self.assertNotEqual(spec['left_native']['dataset_id'], spec['right_native']['dataset_id'])
        self.assertEqual(result['evidence']['right']['route'], 'clef')
        self.assertTrue(result['evidence']['left']['synthetic'])
        self.assertFalse(result['evidence']['right']['live_verified'])
        self.assertEqual(spec['mapping'][0]['left']['request_id'], 'event')

    def test_scientific_spec_is_frozen_before_responses_and_collection(self):
        a, b = manifest(), manifest('clef', replicates=2)
        spec = c.make_pairing_spec(ledger.from_api(a, []), ledger.from_api(b, []))
        left, right = view(a), view(b)
        self.assertEqual(c.make_pairing_spec(left, right), spec)
        empty_collection = {'plan': collection.api_plan(b), 'attempts': [], 'state': 'planned',
                            'provenance': 'synthetic', 'synthetic': True}
        self.assertEqual(c.make_pairing_spec(left, ledger.from_collection(empty_collection)), spec)
        result = c.compare_runs(left, right, pairing=spec)
        self.assertEqual(result['planned'], 2)
        self.assertEqual(result['left']['outcomes']['missing'], 1)
        self.assertEqual(result['left_request_metrics']['requests'], 1)
        self.assertEqual(result['right_request_metrics']['requests'], 2)

    def test_true_task_gold_units_and_measurement_mismatch_rejected(self):
        left = view(manifest())
        for options in ({'gold': .3}, {'text': 'Estimate event B.'}, {'unit': 'percent'}):
            with self.subTest(options=options), self.assertRaisesRegex(c.ComparisonError, 'task/gold/units/measurement'):
                c.make_pairing_spec(left, view(manifest('clef', **options)))
        right = view(manifest('clef'))
        right['trials'][0]['measurement']['id'] = 'classification_error'
        with self.assertRaisesRegex(c.ComparisonError, 'measurement'):
            c.make_pairing_spec(left, right)

    def test_forged_spec_or_task_id_cannot_bypass_mismatch(self):
        left, right = view(manifest()), view(manifest('clef'))
        spec = c.make_pairing_spec(left, right)
        bad = copy.deepcopy(spec)
        bad['mapping'][0]['right']['question_id'] = 'forged'
        with self.assertRaisesRegex(c.ComparisonError, 'frozen scientific'):
            c.compare_runs(left, right, pairing=bad)
        changed = view(manifest('clef', gold=.9))
        changed['task_id'] = left.get('task_id')
        with self.assertRaises(c.ComparisonError):
            c.compare_runs(left, changed, pairing=spec)
        changed['task_contracts'] = right['task_contracts']
        with self.assertRaisesRegex(c.ComparisonError, 'native identity or task contract'):
            c.compare_runs(left, changed, pairing=spec)

    def test_native_planned_set_and_trial_identity_cannot_be_relabelled(self):
        left, right = view(manifest()), view(manifest('clef'))
        spec = c.make_pairing_spec(left, right)
        for field, value in [('request_id', 'other'), ('unit_id', 'other')]:
            bad = copy.deepcopy(right)
            bad['trials'][0][field] = value
            with self.subTest(field=field), self.assertRaises(c.ComparisonError):
                c.compare_runs(left, bad, pairing=spec)
        right['trials'] = []
        with self.assertRaisesRegex(c.ComparisonError, 'full native planned set'):
            c.compare_runs(left, right, pairing=spec)

    def test_failure_never_fabricates_numeric_measurement(self):
        m = manifest()
        missing = ledger.from_api(m, [])
        row = missing['trials'][0]
        self.assertEqual(row['outcome'], 'missing')
        self.assertIsNone(row['measurement']['value'])
        self.assertIsNone(row['correct'])
        self.assertEqual(c.compare_runs(missing, missing)['left']['workflow_loss'], 1)

    def test_heterogeneous_losses_are_reported_separately(self):
        suite = al.load_suite()
        rows = al.select_rows(suite, experiment='probability')
        m = al.prepare_payload(suite, rows, route='decisions')
        left = ledger.from_api(m, al.oracle_entries(m, 'perfect'))
        right = ledger.from_api(m, al.oracle_entries(m, 'wrong'))
        result = c.compare_runs(left, right, bootstrap_samples=50)
        self.assertIsNone(result['estimate']['delta'])
        self.assertIsNone(result['left']['workflow_loss'])
        self.assertEqual(result['estimate']['inference'], 'not-aggregated')
        self.assertEqual(result['planned'], len(left['trials']))
        self.assertEqual({g['measurement']['id'] for g in result['by_measurement']},
                         {'absolute_error', 'classification_error'})
        self.assertEqual(sum(g['report']['planned'] for g in result['by_measurement']), result['planned'])
        self.assertTrue(all(g['report']['estimate']['delta'] is not None for g in result['by_measurement']))

    def test_max_probability_is_not_native_confidence_even_at_same_value(self):
        from tests.test_comparison import trial
        native = {'id': 'native_confidence', 'semantics': 'provider reported; unknown formula',
                  'formula_known': False, 'value': .9}
        maximum = {'id': 'max_probability', 'semantics': 'maximum option mass',
                   'formula_known': True, 'value': .9}
        with self.assertRaisesRegex(c.ComparisonError, 'different selection signals'):
            c.risk_coverage([trial(0, confidence=.9, selection_signal=native),
                             trial(1, confidence=.9, selection_signal=maximum)])

    def test_threshold_keeps_classification_risk_but_never_averages_mixed_loss(self):
        from tests.test_comparison import trial
        rows = [trial(0, loss=.2, measurement={'id': 'absolute_error', 'unit': 'probability', 'semantics': 'distance', 'value': .2}),
                trial(1, loss=1, measurement={'id': 'classification_error', 'unit': 'error', 'semantics': 'mistake', 'value': 1})]
        curve = c.risk_coverage(rows)
        self.assertEqual(curve[-1]['selected'], 2)
        self.assertIsNotNone(curve[-1]['risk'])
        self.assertIsNone(curve[-1]['loss'])

    def test_missing_counterpart_does_not_copy_measurement_or_signal(self):
        left, right = view(manifest()), view(manifest('clef', replicates=2))
        report = c.compare_runs(left, right, pairing=c.make_pairing_spec(left, right))
        absent = next(r for r in report['trace'] if r['left_outcome'] == 'missing')
        self.assertIsNone(absent['left_measurement']['value'])
        self.assertIsNone(absent['left_selection_signal']['value'])

    def test_numeric_old_projection_cannot_silently_mix_with_continuous_loss(self):
        new = view(manifest())
        old = copy.deepcopy(new)
        old['trials'][0].pop('measurement')
        old['trials'][0]['loss'] = 1
        with self.assertRaisesRegex(c.ComparisonError, 'regenerate old ledgers'):
            c.compare_runs(old, new)

    def test_frozen_plan_binds_signal_and_keeps_native_confidence_unknown(self):
        suite = al.load_suite()
        m = al.prepare_payload(suite, suite.rows[:1], route='decisions')
        a = ledger.from_api(m, al.oracle_entries(m))
        b = copy.deepcopy(a)
        a['run_id'], b['run_id'] = 'a', 'b'
        for run in (a, b):
            for row in run['trials']:
                row['split'] = 'test'
        signature = {k: v for k, v in a['trials'][0]['selection_signal'].items() if k != 'value'}
        plan = c.freeze_analysis_plan(dataset_id=a['dataset_id'], comparison=['a', 'b'],
                                      threshold=.5, selection_signal=signature)
        self.assertEqual(c.compare_runs(a, b, plan=plan)['estimate']['delta'], 0)
        wrong = copy.deepcopy(plan)
        wrong['selection_signal']['id'] = 'other:max_probability'
        with self.assertRaisesRegex(c.ComparisonError, 'frozen plan selection signal'):
            c.compare_runs(a, b, plan=wrong)
        self.assertFalse(signature['formula_known'])

    def test_native_signal_semantics_and_threshold_isolation(self):
        # Choice has confidence; Predicate/Noul has no independent confidence.
        suite = al.load_suite()
        rows = suite.rows[:1]
        a = ledger.from_api(al.prepare_payload(suite, rows, route='decisions'), [])
        b = ledger.from_api(al.prepare_payload(suite, rows, route='clef', account_id='a' * 32), [])
        self.assertFalse(a['trials'][0]['selection_signal']['formula_known'])
        with self.assertRaisesRegex(c.ComparisonError, 'different selection signals'):
            c.risk_coverage(a['trials'] + [dict(b['trials'][0], unit_id='other', source_family='other')])
        cal = [dict(a['trials'][0], split='calibration')]
        selection = c.select_threshold(cal)
        test = [dict(b['trials'][0], source_family='held-out', unit_id='held-out', split='test')]
        with self.assertRaisesRegex(c.ComparisonError, 'signal differs'):
            c.evaluate_threshold(test, selection)


if __name__ == '__main__':
    unittest.main()
