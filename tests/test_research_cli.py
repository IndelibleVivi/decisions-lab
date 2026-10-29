import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from decision_lab.cli import main


class ResearchCliTests(unittest.TestCase):
    def command(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_generate_repair_replay_real_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            worlds, record = Path(directory) / "worlds.json", Path(directory) / "record.json"
            self.assertEqual(self.command("research", "generate", "--kind", "rules", "--units", "3", "--output", str(worlds))[0], 0)
            self.assertEqual(self.command("research", "rule-workflow", "--dataset", str(worlds), "--output", str(record))[0], 0)
            code, out, err = self.command("research", "rule-replay", str(record))
            self.assertEqual((code, err), (0, ""))
            self.assertTrue(json.loads(out))

    def test_manifest_oracle_ledger_comparison_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "manifest.json"
            code, out, _ = self.command("api-lab", "prepare", "--route", "decisions", "--experiment", "probability", "--replicates", "2")
            self.assertEqual(code, 0)
            manifest.write_text(out)
            left, right = Path(directory) / "left", Path(directory) / "right"
            for mode, dest in (("perfect", left), ("wrong", right)):
                self.assertEqual(self.command("research", "oracle", "--manifest", str(manifest), "--mode", mode, "--run-dir", str(dest))[0], 0)
            code, out, err = self.command("research", "compare", str(left), str(right))
            self.assertEqual((code, err), (0, ""))
            result = json.loads(out)
            self.assertEqual(result["paired"], 78)
            self.assertIsNone(result["estimate"]["delta"])
            self.assertEqual(len(result["by_measurement"]), 2)
            self.assertTrue(all(group["report"]["estimate"]["delta"] > 0 for group in result["by_measurement"]))
            self.assertIsNone(result["estimate"]["ci95"])

    def test_cross_route_pairing_cli_retains_explicit_spec(self):
        from decision_lab import api_lab, studio
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initial = studio.initial_records(studio.template('api-lab'))
            paths = []
            for key, value in initial.items():
                path = root / (key + '.json')
                record = api_lab.build_record(value['manifest'], api_lab.oracle_entries(value['manifest'], 'perfect'), provenance='synthetic')
                path.write_text(json.dumps(record)); paths.append(str(path))
            self.assertNotEqual(self.command('research', 'compare', *paths)[0], 0)
            spec = str(root / 'pairing.json')
            self.assertEqual(self.command('research', 'pairing', *paths, '--output', spec)[0], 0)
            code, out, err = self.command('research', 'compare', *paths, '--pairing', spec)
            self.assertEqual((code, err), (0, ''))
            report = json.loads(out)
            self.assertEqual(report['paired'], 39)
            self.assertTrue(all(group['report']['estimate']['delta'] == 0 for group in report['by_measurement']))

    def test_collect_requires_permission_switch_via_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            plan = Path(directory) / "plan.json"
            self.assertEqual(self.command("research", "plan", "--kind", "typed-values", "--limit", "1", "--output", str(plan))[0], 0)
            code, _, err = self.command("research", "collect", str(plan), "--run-dir", str(Path(directory) / "run"),
                                        "--max-calls", "1", "--max-questions", "10", "--max-estimated-tokens", "10000")
            self.assertEqual(code, 1)
            self.assertIn("allow-network", err)

    def test_explicit_numeric_partition_is_a_separate_manifest(self):
        code, out, err = self.command("research", "partition-events", "--route", "decisions")
        self.assertEqual((code, err), (0, ""))
        manifest = json.loads(out)
        self.assertEqual(len(manifest["requests"]), 3)
        self.assertEqual(sum(len(r["body"]["questions"]) for r in manifest["requests"]), 12)
        questions = manifest["requests"][-1]["body"]["questions"]
        self.assertIn("{00,01}", questions[-1]["instructions"])

    def test_bad_generator_parameter_reports_readable_error(self):
        code, _, err = self.command("research", "generate", "--kind", "rules", "--units", "0")
        self.assertEqual(code, 1)
        self.assertIn("error:", err)


if __name__ == "__main__":
    unittest.main()
