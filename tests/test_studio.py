"""Research lifecycle, evidence binding and trusted local interpreter boundary."""
import copy
import base64
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from decision_lab import api_lab as al, collection, interpretation, studio


class StudyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = studio.Store(self.directory.name)

    def act(self, study, action, **kwargs):
        return self.store.command(action, {"id": study["id"], "revision": study["revision"], **kwargs})

    def frozen(self, kind="typed-dag"):
        return self.act(self.store.command("create", {"kind": kind}), "freeze")

    def test_three_families_reopen_full_planned_and_no_provider_calls(self):
        with patch('socket.socket', side_effect=AssertionError('provider network forbidden')):
            for kind in ('api-lab', 'active-evidence', 'typed-dag'):
                with self.subTest(kind=kind):
                    study = self.frozen(kind)
                    initial = copy.deepcopy(study['analyses'][0])
                    study = self.act(study, 'run')
                    self.assertEqual(study['analyses'][0], initial)
                    self.assertEqual(len(study['analyses']), 2)
                    self.assertTrue(all(len(v) == 2 for v in study['runs'].values()))
                    reopened = studio.Store(self.directory.name).get(study['id'])
                    self.assertEqual(reopened, study)
                    result = reopened['analyses'][-1]['result']
                    self.assertFalse(result['live_verified'])
                    self.assertTrue(all(c['report']['synthetic'] is True for c in result['conditions'].values()))
                    self.assertIsNone(result['comparisons'][0]['error'])

    def test_stale_save_does_not_erase_another_revision(self):
        study = self.store.command('create', {'kind': 'typed-dag'})
        draft = copy.deepcopy(study['definition']); draft['title'] = 'changed'
        current = self.act(study, 'save', definition=draft)
        with self.assertRaisesRegex(ValueError, 'revision conflict'):
            self.act(study, 'save', definition=study['definition'])
        self.assertEqual(self.store.get(study['id']), current)

    def test_frozen_design_cannot_change_and_fork_has_no_old_results(self):
        study = self.act(self.frozen(), 'run')
        with self.assertRaisesRegex(ValueError, 'frozen'):
            self.act(study, 'save', definition=study['definition'])
        fork = self.act(study, 'fork')
        self.assertEqual(fork['definition'], study['definition'])
        self.assertEqual(fork['parent']['id'], study['id'])
        self.assertFalse(fork['runs']); self.assertFalse(fork['analyses'])
        self.assertEqual(self.store.get(study['id']), study)

    def test_historical_and_current_interpretations_remain_separate(self):
        study = self.act(self.frozen(), 'run')
        original = copy.deepcopy(study['analyses'][-1])
        study = self.act(study, 'reproduce', analysis=original['id'])
        self.assertTrue(study['analyses'][-1]['diff']['equal'])
        self.assertEqual(study['analyses'][-1]['run_ids'], original['run_ids'])
        base = interpretation.analyse
        def changed(payload):
            result = base(payload); result['changed_definition'] = True; return result
        with patch.object(interpretation, 'analyse', changed):
            study = self.act(study, 'reanalyse', analysis=original['id'])
        self.assertFalse(study['analyses'][-1]['diff']['equal'])
        self.assertEqual(study['analyses'][1], original)

    def test_modified_retained_code_is_never_executed(self):
        study = self.frozen(); original = study['analyses'][0]
        path = self.store.sources / original['interpreter']['id'] / 'decision_lab' / 'interpretation.py'
        path.write_text('raise RuntimeError("must not execute")')
        with self.assertRaisesRegex(ValueError, 'source changed'):
            self.act(study, 'reproduce', analysis=original['id'])
        self.assertEqual(len(self.store.get(study['id'])['analyses']), 1)

    def test_import_has_no_executable_snapshot_and_retains_source_claim(self):
        study = self.act(self.frozen(), 'run')
        bundle = self.store.export(study['id'])
        with tempfile.TemporaryDirectory() as destination:
            other = studio.Store(destination)
            imported = other.command('import-bundle', {'bundle': bundle})
            self.assertEqual(imported['analyses'][1]['result'], study['analyses'][1]['result'])
            self.assertIn('not independently authenticated', imported['analyses'][1]['origin'])
            # Import runs a fresh local analysis. A foreign old interpreter cannot be supplied as JSON.
            foreign = copy.deepcopy(imported['analyses'][1]['interpreter']);foreign['id'] = '0' * 64
            with self.assertRaisesRegex(ValueError, 'unavailable'):
                other._historical(foreign, {'records': {}})
            self.assertNotEqual(imported['id'], study['id'])

    def test_import_rejects_design_manifest_disagreement(self):
        study = self.frozen(); bundle = self.store.export(study['id'])
        bad = bundle['study']; bad['definition']['replicates'] = 2
        bad['frozen']['design_digest'] = al.digest(bad['definition']);studio.seal(bad)
        with self.assertRaisesRegex(ValueError, 'disagree'):
            self.store.command('import-bundle', {'bundle': bundle})

    def test_wrong_condition_import_is_atomic(self):
        study = self.act(self.frozen(), 'run'); before = self.store.get(study['id'])
        foreign = study['runs']['b'][-1]['record']
        with self.assertRaisesRegex(ValueError, 'differs from frozen'):
            self.act(study, 'import-record', condition='a', record=foreign)
        self.assertEqual(self.store.get(study['id']), before)

    def test_notes_bind_analysis_and_counterexample(self):
        study = self.act(self.frozen(), 'run'); analysis = study['analyses'][-1]['id']
        study = self.act(study, 'note', text='schema insufficiency remains', counterexample='schema-gap-continue', analysis=analysis)
        study = self.act(study, 'reanalyse', analysis=analysis)
        self.assertEqual(study['notes'][0]['analysis'], analysis)
        self.assertEqual(study['notes'][0]['counterexample'], 'schema-gap-continue')

    def test_partial_api_answers_keep_planned_missing(self):
        study = self.frozen('api-lab'); manifest = study['frozen']['initial']['a']['manifest']
        entries = al.oracle_entries(manifest)[:1]
        value = {'schema': al.RESPONSE_VERSION, 'responses': entries, 'synthetic': True}
        study = self.act(study, 'import-record', condition='a', record=value)
        coverage = study['analyses'][-1]['result']['conditions']['a']['report']['coverage']
        self.assertEqual(coverage['received_requests'], 1)
        self.assertEqual(coverage['missing_requests'], len(manifest['requests'])-1)
        self.assertEqual(study['runs']['a'][-1]['record']['provenance'], 'imported')

    def test_safe_paths_and_null_differences(self):
        with self.assertRaisesRegex(ValueError, 'invalid study ID'):
            self.store.get('../secret')
        diff = interpretation.differences({}, {'answer': None})
        self.assertFalse(diff['equal']); self.assertFalse(diff['changes'][0]['before_present'])
        self.assertTrue(diff['changes'][0]['after_present'])

    def test_empty_evidence_requires_explicit_partial_mode(self):
        manifest = studio.initial_records(studio.template('api-lab'))['a']['manifest']
        with self.assertRaisesRegex(ValueError, 'nonempty'):
            al.build_record(manifest, [], provenance='imported')
        record = al.build_record(manifest, [], provenance='imported', allow_partial=True)
        report = interpretation.evaluate_record(record)['report']
        self.assertEqual(report['coverage']['missing_question_slots'], report['coverage']['expected_questions'])

    def test_collection_import_keeps_bytes_attempts_and_missing(self):
        study = self.frozen('api-lab')
        manifest = study['frozen']['initial']['a']['manifest']
        entry = al.oracle_entries(manifest, 'perfect')[0]
        raw = base64.b64encode(json.dumps(entry['response']).encode()).decode()
        retained = collection._seal({'schema': collection.SCHEMA, 'plan': collection.api_plan(manifest),
            'provenance': 'collector', 'synthetic': True, 'live_verified': False,
            'order': [r['id'] for r in manifest['requests']], 'state': 'cancelled',
            'attempts': [{'request_id': entry['request_id'], 'attempt': 0, 'state': 'ok',
                          'delivery': 'received', 'parsed': entry['response'], 'raw_body_base64': raw,
                          'http_status': 200, 'elapsed_ms': 3, 'usage': None, 'cost': None}]})
        with patch('socket.socket', side_effect=AssertionError('network forbidden')):
            study = self.act(study, 'import-record', condition='a', record=retained)
        self.assertEqual(study['runs']['a'][-1]['record'], retained)
        evaluated = study['analyses'][-1]['result']['conditions']['a']
        self.assertGreater(evaluated['report']['coverage']['missing_question_slots'], 0)
        self.assertEqual(evaluated['ledger']['attempts'][0]['latency_ms'], 3)
        self.assertEqual(evaluated['ledger']['provenance'], 'collector')
        imported = self.store.command('import-bundle', {'bundle': self.store.export(study['id'])})
        self.assertEqual(imported['runs']['a'][-1]['record'], retained)

    def test_text_upload_preserves_native_json_and_rejects_duplicate_keys(self):
        study = self.act(self.frozen('api-lab'), 'run')
        raw = json.dumps(self.store.export(study['id']))
        imported = self.store.command('import-bundle', {'bundle_json': raw})
        self.assertEqual(imported['runs'], study['runs'])
        self.assertEqual(imported['analyses'][1]['result'], study['analyses'][1]['result'])
        with self.assertRaisesRegex(ValueError, 'duplicate JSON'):
            self.store.command('import-bundle', {'bundle_json': '{"schema":1,"schema":2}'})


@unittest.skipUnless(importlib.util.find_spec('markdown_it'), 'HTTP reader integration requires requirements-site.txt')
class StudioHTTPTests(unittest.TestCase):
    def test_same_frontend_host_origin_token_and_private_path_boundary(self):
        from decision_lab.studio_server import make_server
        with tempfile.TemporaryDirectory() as directory:
            server = make_server(directory, 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            try:
                base = f'http://127.0.0.1:{server.server_port}'
                body = urlopen(base).read().decode()
                self.assertIn('id="sculpture-canvas"', body)
                self.assertIn('id="playground"', body)
                self.assertIn('id="research-studio"', body)
                import re
                token = re.search(r'<meta name="studio-token" content="([^"]+)"', body)[1]
                for headers in ({'Host': 'attacker.test'}, {'Origin': 'https://attacker.test'}):
                    with self.assertRaises(HTTPError) as err: urlopen(Request(base+'/api/studies', headers=headers))
                    self.assertEqual(err.exception.code, 403)
                data = json.dumps({'kind':'typed-dag'}).encode()
                with self.assertRaises(HTTPError) as err:
                    urlopen(Request(base+'/api/action/create', data=data, headers={'Content-Type':'application/json'}))
                self.assertEqual(err.exception.code, 403)
                result = json.load(urlopen(Request(base+'/api/action/create', data=data, headers={'Content-Type':'application/json','X-Studio-Token':token})))
                self.assertEqual(result['state'], 'draft')
                for path in ('/runs/studio/secret.json', '/site/studio.html', '/../AGENTS.md'):
                    with self.assertRaises(HTTPError) as err: urlopen(base+path)
                    self.assertEqual(err.exception.code, 404)
            finally:
                server.shutdown();server.server_close();thread.join(timeout=3)


if __name__ == '__main__':
    unittest.main()
