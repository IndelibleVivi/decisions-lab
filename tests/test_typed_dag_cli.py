"""Exercise the public dependent-stage CLI without provider access."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from decision_lab.cli import main
from decision_lab import collection, typed_values as tv, api_lab as al
from decision_lab.live import TransportResponse


class TypedDagCliTests(unittest.TestCase):
    def command(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["research", *args])
        return code, out.getvalue(), err.getvalue()

    def test_public_demo_persists_and_replays_without_network(self):
        with tempfile.TemporaryDirectory() as directory, patch("socket.socket", side_effect=AssertionError("network forbidden")):
            root = Path(directory)
            suite, record = root / "suite.json", root / "workflow.json"
            self.assertEqual(self.command("typed-dag-suite", "--output", str(suite))[0], 0)
            code, _, err = self.command("typed-dag-demo", "--suite", str(suite), "--route", "decisions", "--output", str(record))
            self.assertEqual((code, err), (0, ""))
            code, out, err = self.command("typed-dag-report", str(record))
            self.assertEqual((code, err), (0, ""))
            report = json.loads(out)
            self.assertTrue(report)
            self.assertIs(report["live_verified"], False)
            self.assertEqual(self.command("typed-dag-prepare", str(record))[1].strip(), "null")
            code, out, err = self.command("typed-dag-compare", str(record), str(record))
            self.assertEqual((code, err), (0, ""))
            self.assertTrue(json.loads(out))
            before = record.read_bytes()
            code, _, err = self.command("typed-dag-start", "--output", str(record))
            self.assertEqual(code, 1)
            self.assertIn("already exists", err)
            self.assertEqual(record.read_bytes(), before)

    def test_saved_native_collection_and_record_advance_both_public_stages(self):
        with tempfile.TemporaryDirectory() as directory, patch("socket.socket", side_effect=AssertionError("network forbidden")):
            root = Path(directory)
            state0, state1, state2 = [root / f"state-{i}.json" for i in range(3)]
            self.assertEqual(self.command("typed-dag-start", "--output", str(state0))[0], 0)
            plan0 = json.loads(self.command("typed-dag-prepare", str(state0))[1])
            typed_suite_path = root / "typed-suite.json"
            typed_suite_path.write_text(json.dumps(plan0["suite"]), encoding="utf-8")
            typed_suite = tv.load_suite(typed_suite_path)
            cases = {case.state: case for case in typed_suite.cases}

            class MockClairic:
                def post_json(self, endpoint, headers, body):
                    case = cases[body["state"]]
                    answers = tv._demo_answers(case)
                    for answer in answers.values():
                        if answer["type"] == "number" and answer["value"] is None:
                            answer.update(guess=99.99, p_null=0.9)
                    raw = {"model": "clairic", "answers": answers,
                           "truncated": False, "usage": {"input_tokens": 0, "output_tokens": 0}}
                    return TransportResponse(200, json.dumps(raw).encode(), 0)

            run = root / "typed-collection"
            native_collection = collection.collect(
                plan0, run, allow_network=True, client=MockClairic(),
                credential="synthetic-test-key", account_id="a" * 32,
                max_calls=len(plan0["requests"]), max_questions=1000,
                max_estimated_tokens=1000000)
            native_collection["synthetic"] = True
            native_collection["evidence_digest"] = al.digest({
                k: v for k, v in native_collection.items() if k != "evidence_digest"})
            typed_path = run / "collection.json"
            typed_path.write_text(json.dumps(native_collection), encoding="utf-8")
            code, _, err = self.command("typed-dag-apply", str(state0), str(typed_path), "--output", str(state1))
            self.assertEqual((code, err), (0, ""))
            plan1 = json.loads(self.command("typed-dag-prepare", str(state1))[1])
            collection.validate_plan(plan1)
            self.assertEqual(plan1["kind"], "api-lab")
            native = al.build_record(plan1["manifest"], al.oracle_entries(plan1["manifest"], mode="perfect"), provenance="synthetic")
            native_path = root / "decision-record.json"
            native_path.write_text(json.dumps(native), encoding="utf-8")
            code, _, err = self.command("typed-dag-apply", str(state1), str(native_path), "--output", str(state2))
            self.assertEqual((code, err), (0, ""))
            self.assertEqual(self.command("typed-dag-prepare", str(state2))[1].strip(), "null")
            code, out, err = self.command("typed-dag-report", str(state2))
            self.assertEqual((code, err), (0, ""))
            replay = json.loads(out)
            self.assertIs(replay["live_verified"], False)
            missing_operand = next(row for row in replay["rows"] if row["case_id"] == "missing-operand")
            self.assertIsNone(missing_operand["adopted_fields"]["shipping"])
            self.assertIsNone(missing_operand["calculation"]["total"])
            self.assertEqual(self.command("typed-dag-apply", str(state1), str(typed_path))[0], 1)

    def test_first_stage_is_a_valid_retained_typed_collection_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            self.assertEqual(self.command("typed-dag-start", "--output", str(state))[0], 0)
            code, out, err = self.command("typed-dag-prepare", str(state))
            self.assertEqual((code, err), (0, ""))
            plan = json.loads(out)
            collection.validate_plan(plan)
            self.assertEqual(plan["kind"], "typed-values")
            self.assertNotIn("editorial_oracle", json.dumps([r["body"] for r in plan["requests"]]))


if __name__ == "__main__":
    unittest.main()
