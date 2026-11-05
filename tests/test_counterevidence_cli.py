"""Exercise the public counterevidence authoring and retained E2 entry points."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CounterevidenceCliTests(unittest.TestCase):
    def command(self, *args):
        result = subprocess.run([sys.executable, '-m', 'decision_lab', 'research',
                                 *map(str, args)], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_author_prepare_replay_and_compare_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            design, suite = root / 'design.json', root / 'suite.json'
            self.command('counterevidence-design', '--output', design)
            self.command('counterevidence-suite', design, '--output', suite)
            for mode in ('no-query', 'adaptive', 'read-all'):
                run = root / (mode + '.json')
                self.command('evidence-demo', '--suite', suite, '--query-mode', mode,
                             '--policy', 'stop' if mode == 'no-query' else 'optimal', '--output', run)
                report = self.command('evidence-report', run)
                self.assertEqual(report['summary']['planned'], 12)
                self.assertEqual(report['summary']['missing'], 0)
                self.assertTrue(report['synthetic'])
                self.assertIsNone(self.command('evidence-prepare', run))
            comparison = self.command('evidence-compare', root / 'read-all.json', root / 'adaptive.json')
            self.assertIn('summary', comparison)
            state = root / 'pending.json'
            self.command('evidence-start', '--suite', suite, '--route', 'decisions',
                         '--model', 'gpt-6-luna', '--query-mode', 'no-query', '--output', state)
            plan = self.command('evidence-prepare', state)
            self.assertEqual(len(plan['requests']), 12)
            for request in plan['requests']:
                body = request['body']
                self.assertEqual(body['model'], 'gpt-6-luna')
                self.assertTrue(all(not str(c['value']).startswith('query:')
                                    for c in body['questions'][0]['choices']))


if __name__ == '__main__':
    unittest.main()
