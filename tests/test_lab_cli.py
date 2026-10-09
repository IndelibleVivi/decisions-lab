"""CLI behaviour tests: readable errors and nonzero exits for bad input."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

from decision_lab.cli import main

REPO = Path(__file__).resolve().parent.parent
SUITE_PATH = REPO / "experiments" / "next-action" / "cases.json"


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


class TestCli(unittest.TestCase):
    def test_validate_ok(self):
        code, out, _ = _run(["validate", str(SUITE_PATH)])
        self.assertEqual(code, 0)
        self.assertIn("OK", out)

    def test_validate_missing_file_nonzero(self):
        code, _, err = _run(["validate", "/nope/missing.json"])
        self.assertEqual(code, 1)
        self.assertTrue(err.strip())

    def test_baseline_run_writes_record(self):
        with tempfile.TemporaryDirectory() as d:
            code, out, _ = _run(["baseline-run", str(SUITE_PATH), "--run-dir", str(Path(d) / "r")])
            self.assertEqual(code, 0)
            self.assertTrue((Path(d) / "r" / "record.json").is_file())

    def test_prepare_has_no_network_and_shows_route(self):
        code, out, _ = _run(["prepare", str(SUITE_PATH), "--route", "jev", "--limit", "1"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["route"], "jev")
        self.assertEqual(payload["docs_verified_at"], "2026-10-09")
        self.assertFalse(payload["live_verified"])
        # request carries the documented shape and no local request id
        body = payload["requests"][0]["body"]
        self.assertEqual(set(body), {"model", "state", "questions"})

    def test_prepare_unknown_route_nonzero(self):
        # argparse rejects an invalid choice with a nonzero SystemExit
        with self.assertRaises(SystemExit) as ctx:
            _run(["prepare", str(SUITE_PATH), "--route", "nope"])
        self.assertEqual(ctx.exception.code, 2)

    def test_collect_live_without_switch_refused(self):
        with tempfile.TemporaryDirectory() as d:
            code, _, err = _run(
                ["collect-live", str(SUITE_PATH), "--route", "jev",
                 "--run-dir", str(Path(d) / "live"), "--max-calls", "1"]
            )
            self.assertEqual(code, 2)
            self.assertIn("allow-network", err)

    def test_help_works(self):
        with self.assertRaises(SystemExit) as ctx:
            _run(["--help"])
        self.assertEqual(ctx.exception.code, 0)

    def test_replay_missing_record_nonzero(self):
        code, _, err = _run(["replay", "/nope/record.json", str(SUITE_PATH)])
        self.assertEqual(code, 1)
        self.assertTrue(err.strip())


class TestDefaultSuiteShortcuts(unittest.TestCase):
    """validate/demo/replay must work with the default suite (no argument)."""

    def test_validate_uses_default_suite(self):
        code, out, _ = _run(["validate"])
        self.assertEqual(code, 0)
        self.assertIn("OK", out)

    def test_demo_uses_default_suite(self):
        with tempfile.TemporaryDirectory() as d:
            code, out, _ = _run(["demo", "--run-dir", str(Path(d) / "demo")])
            self.assertEqual(code, 0)
            self.assertIn("SYNTHETIC", out)
            self.assertTrue((Path(d) / "demo" / "record.json").is_file())

    def test_replay_uses_default_suite(self):
        with tempfile.TemporaryDirectory() as d:
            run = Path(d) / "demo"
            code, _, _ = _run(["demo", "--run-dir", str(run)])
            self.assertEqual(code, 0)
            code, out, _ = _run(["replay", str(run)])
            self.assertEqual(code, 0)
            payload = json.loads(out)
            self.assertEqual(payload["evaluation"]["total"], 25)

    def test_routes_reports_docs_verified(self):
        code, out, _ = _run(["routes"])
        self.assertEqual(code, 0)
        meta = json.loads(out)["protocol_provenance"]
        self.assertEqual(meta["docs_verified_at"], "2026-10-09")
        self.assertFalse(meta["live_verified"])


if __name__ == "__main__":
    unittest.main()
