import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from decision_lab import api_lab as al, ledger, typed_values as tv
from decision_lab import record as legacy
from decision_lab.cases import load_suite
from decision_lab.conformance import prepare_probes


class LedgerTests(unittest.TestCase):
    def test_api_planned_missing_and_model_defaults(self):
        manifest = prepare_probes("decisions")
        entries = al.oracle_entries(manifest)
        with patch.dict(al.DEFAULT_MODELS, {"decisions": "new-default"}):
            view = ledger.from_api(manifest, entries[:1])
        self.assertEqual(len(view["trials"]), 6)
        self.assertEqual(sum(r["outcome"] == "missing" for r in view["trials"]), 5)
        self.assertEqual(len(view["requests"]), 1)
        changed = copy.deepcopy(manifest)
        changed["model"] = "new-model"
        for r in changed["requests"]:
            r["body"]["model"] = "new-model"
            r["request_digest"] = al.digest({"body": r["body"], "required_headers": r["required_headers"]})
        changed["manifest_digest"] = al.digest({k: v for k, v in changed.items() if k != "manifest_digest"})
        self.assertEqual(ledger.from_api(changed, [])["dataset_id"], view["dataset_id"])
        changed["requests"][0]["body"]["input"] = "different source"
        r = changed["requests"][0]
        r["request_digest"] = al.digest({"body": r["body"], "required_headers": r["required_headers"]})
        changed["manifest_digest"] = al.digest({k: v for k, v in changed.items() if k != "manifest_digest"})
        self.assertNotEqual(ledger.from_api(changed, [])["dataset_id"], view["dataset_id"])

    def test_empty_api_entries_are_all_missing(self):
        view = ledger.from_api(prepare_probes("jev"), [])
        self.assertEqual(len(view["trials"]), 6)
        self.assertTrue(all(r["outcome"] == "missing" for r in view["trials"]))

    def test_legacy_readonly_subset_and_unknown_plan(self):
        suite = load_suite("experiments/next-action/cases.json")
        record = legacy.run_baseline(suite, suite_path="experiments/next-action/cases.json")
        record.results = record.results[:1]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "record.json"
            path.write_text(json.dumps(record.as_dict()))
            view = ledger.load_ledger(path)
            self.assertEqual(len(view["trials"]), len(suite.cases))
            self.assertEqual(sum(t["outcome"] == "missing" for t in view["trials"]), 24)
            record.planned_case_ids = [record.results[0].case_id]
            path.write_text(json.dumps(record.as_dict()))
            view = ledger.load_ledger(path)
            self.assertEqual(len(view["trials"]), 1)
            self.assertEqual(legacy.evaluate(record, suite).total, 1)
            before = path.read_bytes()
            ledger.load_ledger(path)
            self.assertEqual(before, path.read_bytes())

    def test_probe_shape_and_native_oracle_roundtrip(self):
        for route in ("jev", "decisions"):
            manifest = prepare_probes(route)
            self.assertEqual(al.validate_manifest(manifest), {"requests": 4, "questions": 6})
            report = al.evaluate(manifest, al.oracle_entries(manifest))
            self.assertEqual(report["accuracy_on_valid_answers"], 1.0)
            self.assertTrue(all(q["outcome"] == "ok" for r in report["requests"] for q in r["questions"]))


if __name__ == "__main__":
    unittest.main()
