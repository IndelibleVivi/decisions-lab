"""Finite source rules, model visibility, and existing E2 round boundaries."""
import copy
import json
import unittest
from unittest.mock import patch

from decision_lab import api_lab as al, counterevidence as ce, evidence as ev
from decision_lab import evidence_workflow as ew
from tests.test_evidence_workflow import fixture, collected


class CounterevidenceTests(unittest.TestCase):
    def setUp(self):
        self.design = ce.build_design()
        self.suite = ce.compile_suite(self.design)

    def scenario(self, name):
        return next(s for s in self.suite['scenarios'] if s['id'] == name)

    def test_source_rules_determine_ground_truth_and_unavailable_does_not_erase_it(self):
        expected = {'stale-version': ['allow', 'hold'], 'wrong-entity': ['hold', 'allow'],
                    'omitted-exception': ['hold', 'allow'], 'unsupported-authority': ['hold', 'allow'],
                    'unavailable-source': ['hold', 'allow'], 'already-sufficient': ['allow', 'allow']}
        for family in self.design['families']:
            scenario = self.scenario(family['id'])
            for case, gold in zip(family['cases'], expected[family['id']]):
                self.assertEqual(ce._resolved_decision(case), gold)
                for decision in scenario['decisions']:
                    self.assertEqual(decision['losses'][case['id']], 0 if decision['id'] == gold else 10)
        # A newer-looking draft and a different entity cannot override authority.
        case = copy.deepcopy(self.design['families'][3]['cases'][0])
        case['sources'][0]['effective_from'] = 2026
        self.assertEqual(ce._resolved_decision(case), 'hold')

    def test_initial_native_bodies_are_equal_within_pairs_and_hide_world_model(self):
        for route in ('decisions', 'jev', 'openrouter-decisions'):
            workflow = ew.start(self.suite, route=route)
            grouped = {}
            for request in ew.prepare_round(workflow)['requests']:
                body = request['body']; family = request['trial']['source_family']
                self.assertEqual(grouped.setdefault(family, body), body)
                visible = json.loads(body.get('input', body.get('state')))
                self.assertEqual(visible['revealed'], [])
                text = json.dumps(body)
                for forbidden in ('hypotheses', 'posterior', 'world_id', 'resolved_decision',
                                  'compatible_hypotheses', 'source_family', 'proposition'):
                    self.assertNotIn(forbidden, text)
                self.assertNotIn(family, text)
                self.assertNotIn(request['trial']['unit_id'], text)

    def test_only_queried_source_reveals_and_unicode_locators_cover_actual_text(self):
        for family in self.design['families']:
            scenario = self.scenario(family['id'])
            for case in family['cases']:
                for query in scenario['queries']:
                    state = ev.step(scenario, ev.initial_state(scenario, case['id']), 'query:'+query['id'])
                    visible = ce.visible_state(scenario, state)
                    self.assertEqual(len(visible['revealed']), 1)
                    obs = visible['revealed'][0]
                    source = next(s for s in case['sources'] if s['id'] == obs['source_id'])
                    if source['available']:
                        locator = obs['locator']
                        self.assertEqual(source['text'][locator['start']:locator['end']], obs['excerpt'])
                        self.assertEqual(locator['unit'], 'unicode_codepoint')
                    else:
                        self.assertEqual(set(obs), {'source_id', 'available', 'notice'})
                        self.assertNotIn(source['text'], json.dumps(visible, ensure_ascii=False))

    def test_unavailable_worlds_remain_indistinguishable_after_all_queries(self):
        scenario = self.scenario('unavailable-source')
        states = [ev.initial_state(scenario, h['id']) for h in scenario['hypotheses']]
        for query in scenario['queries']:
            states = [ev.step(scenario, state, 'query:'+query['id']) for state in states]
        self.assertEqual(ce.visible_state(scenario, states[0]), ce.visible_state(scenario, states[1]))
        self.assertTrue(all(ev.oracle(scenario, s)['action'] == 'abstain' for s in states))

    def test_normal_control_has_original_evidence_already_visible(self):
        scenario = self.scenario('already-sufficient')
        state = ev.initial_state(scenario, scenario['hypotheses'][0]['id'])
        visible = ce.visible_state(scenario, state)
        attached = visible['initial_dossier']['attached_sources'][0]
        self.assertEqual(attached['authority'], 'origin')
        self.assertEqual(attached['entity'], visible['target'])
        self.assertEqual(attached['effective_from'], visible['decision_time'])
        self.assertIn('可以启用', attached['excerpt'])
        self.assertEqual(ev.oracle(scenario, state)['action'], 'commit:allow')

    def test_exact_controls_and_request_counts_are_separate_from_live_calls(self):
        with patch('socket.socket', side_effect=AssertionError('no network')):
            expected = {'no-query': (30, 0, 12), 'adaptive': (14, 8, 20), 'read-all': (26, 20, 12)}
            for mode, (loss, reads, requests) in expected.items():
                workflow = ew.demo(self.suite, query_mode=mode, policy='optimal')
                report = ew.report(workflow)
                self.assertEqual(report['summary']['total_loss'], loss)
                self.assertEqual(report['summary']['query_cost'], reads)
                self.assertEqual(report['summary']['planned'], 12)
                self.assertEqual(report['summary']['missing'], 0)
                self.assertEqual(report['native']['request_count'], requests)
                self.assertTrue(report['synthetic'])
                self.assertIsNone(ew.prepare_round(workflow))
                self.assertEqual(ew.report(json.loads(json.dumps(workflow))), report)

    def test_no_query_cannot_execute_a_query(self):
        workflow = ew.start(self.suite, route='decisions', query_mode='no-query')
        manifest = ew.prepare_round(workflow)
        for request in manifest['requests']:
            self.assertFalse(any(c['value'].startswith('query:') for c in request['body']['questions'][0]['choices']))
        source = fixture(workflow, lambda visible, plan: 'query:version')
        before = copy.deepcopy(workflow)
        # The existing native normalizer classifies an unlisted action as API
        # error; it must never execute the query or become a business abstain.
        rejected = ew.report(ew.apply_round(workflow, source))
        self.assertEqual(rejected['summary']['failure_statuses']['error'], 12)
        self.assertEqual(rejected['summary']['query_cost'], 0)
        self.assertEqual(rejected['summary']['abstained'], 0)
        self.assertEqual(workflow, before)

    def test_pending_and_native_failure_are_not_business_disagreement(self):
        workflow = ew.start(self.suite, route='decisions')
        pending = ew.report(workflow)
        self.assertEqual(pending['summary']['missing'], 12)
        self.assertTrue(all(r['counterevidence_evidence']['diagnostics']['acted_against_initial_claim'] is None
                            for r in pending['episodes']))
        failed = ew.apply_round(workflow, fixture(workflow, lambda visible, plan: 'unknown'))
        report = ew.report(failed)
        self.assertEqual(report['summary']['api_failed'], 12)
        self.assertEqual(report['summary']['abstained'], 0)
        self.assertTrue(all(r['counterevidence_evidence']['diagnostics']['acted_against_initial_claim'] is None
                            for r in report['episodes']))

    def test_partial_and_uncertain_sources_do_not_advance_any_episode(self):
        workflow = ew.start(self.suite, route='decisions')
        before = copy.deepcopy(workflow)
        source = fixture(workflow, lambda visible, plan: 'abstain')
        source['responses'].pop(); ew._seal(source)
        with self.assertRaisesRegex(ValueError, 'missing responses'):
            ew.apply_round(workflow, source)
        source = collected(fixture(workflow, lambda visible, plan: 'abstain'))
        source['attempts'][0].update(state='transport_error', delivery='uncertain', parsed=None,
                                     raw_body_base64=None, parse_status='not_received')
        ew._seal(source)
        with self.assertRaisesRegex(ValueError, 'uncertain'):
            ew.apply_round(workflow, source)
        self.assertEqual(workflow, before)

    def test_suite_recompile_and_mode_bindings_reject_tampering(self):
        changed = copy.deepcopy(self.suite)
        changed['scenarios'][0]['counterevidence_initial']['claim'] = 'hold'
        with self.assertRaisesRegex(ValueError, 'compiled evidence suite'):
            ew.start(changed, route='decisions')
        changed = copy.deepcopy(self.design); changed['rules'] = 'always allow'
        with self.assertRaisesRegex(ValueError, 'finite evaluator'):
            ce.compile_suite(changed)
        changed = copy.deepcopy(self.design)
        changed['families'][0]['cases'][1]['initial']['claim'] = 'hold'
        with self.assertRaisesRegex(ValueError, 'identical initial'):
            ce.compile_suite(changed)
        adaptive = ew.start(self.suite, route='decisions')
        terminal_only = ew.start(self.suite, route='decisions', query_mode='no-query')
        with self.assertRaisesRegex(ValueError, 'current round'):
            ew.apply_round(terminal_only, fixture(adaptive, lambda visible, plan: 'abstain'))


if __name__ == '__main__':
    unittest.main()
