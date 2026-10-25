"""User entry points for the offline, dependent-round evidence workflow."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from decision_lab.cli import main


class EvidenceCliTests(unittest.TestCase):
    def command(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["research", *args])
        return code, out.getvalue(), err.getvalue()

    def test_native_demo_round_trip_comparison_and_no_network(self):
        with tempfile.TemporaryDirectory() as directory, patch("socket.socket", side_effect=AssertionError("network forbidden")):
            root = Path(directory)
            baseline, workflow = root / "myopic.json", root / "workflow.json"
            self.assertEqual(self.command("evidence-run", "--policy", "myopic", "--output", str(baseline))[0], 0)
            code, _, err = self.command("evidence-demo", "--route", "decisions", "--output", str(workflow))
            self.assertEqual((code, err), (0, ""))
            code, out, err = self.command("evidence-report", str(workflow))
            self.assertEqual((code, err), (0, ""))
            report = json.loads(out)
            self.assertEqual(report["summary"]["planned"], 16)
            self.assertEqual(report["summary"]["missing"], 0)
            self.assertTrue(report["synthetic"])
            self.assertEqual(report["native"]["turns"], 3)
            code, out, err = self.command("evidence-compare", str(baseline), str(workflow))
            self.assertEqual((code, err), (0, ""))
            xor = json.loads(out)["families"]["xor-complement"]["total_loss"]
            self.assertEqual(xor["left"], 3)
            self.assertEqual(xor["right"], 2)
            self.assertEqual(self.command("evidence-prepare", str(workflow))[1].strip(), "null")
            original = workflow.read_bytes()
            code, _, err = self.command("evidence-start", "--route", "decisions", "--output", str(workflow))
            self.assertEqual(code, 1)
            self.assertIn("already exists", err)
            self.assertEqual(workflow.read_bytes(), original)

    def test_uncollected_plan_keeps_all_missing_and_native_projection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pending.json"
            self.assertEqual(self.command("evidence-start", "--route", "jev", "--output", str(path))[0], 0)
            code, out, err = self.command("evidence-report", str(path))
            self.assertEqual((code, err), (0, ""))
            self.assertEqual(json.loads(out)["summary"]["missing"], 16)
            code, out, err = self.command("evidence-prepare", str(path))
            self.assertEqual((code, err), (0, ""))
            manifest = json.loads(out)
            self.assertEqual(len(manifest["requests"]), 16)
            self.assertNotIn("world_id", json.dumps([r["body"] for r in manifest["requests"]]))
            self.assertIn("state", manifest["requests"][0]["body"])

    def test_bad_suite_and_protected_output_are_readable_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text('{"schema": "wrong"}')
            code, _, err = self.command("evidence-run", "--suite", str(path))
            self.assertEqual(code, 1)
            self.assertIn("invalid evidence suite", err)
        code, _, err = self.command("evidence-suite", "--output", "catalog/no-evidence-output.json")
        self.assertEqual(code, 1)
        self.assertIn("must be under runs/", err)


if __name__ == "__main__":
    unittest.main()
