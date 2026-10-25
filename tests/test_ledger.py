import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from decision_lab import api_lab as al, ledger, role_tasks as roles, typed_values as tv
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


def reseal_manifest(manifest):
    for request in manifest["requests"]:
        request["rubric_digest"] = al.digest(request["rubric"])
    manifest["manifest_digest"] = al.digest({k: v for k, v in manifest.items() if k != "manifest_digest"})


class RoleLedgerTests(unittest.TestCase):
    def test_retained_role_scores_and_guard_match_specialized_report(self):
        for route in ("decisions", "jev"):
            manifest = roles.prepare(route, replicates=1)
            entries = roles.baseline_entries(manifest, "first")
            report = roles.evaluate(manifest, entries)
            native = {r["request_id"]: r["questions"][0] for r in report["api_report"]["requests"]}
            view = ledger.from_api(manifest, entries)
            projected = {r["request_id"]: r for r in view["trials"]}
            for row in report["requests"]:
                trial = projected[row["request_id"]]
                for field in ("outcome", "correct", "choice", "semantic_action", "unsafe", "guard_rejected", "loss"):
                    self.assertEqual(trial[field], row[field], (row["request_id"], field))
                self.assertEqual(trial["metric"], "role_workflow_loss")
                self.assertEqual(trial["retained_failure_loss"], roles.LOSS["failure_or_missing"])
                self.assertEqual(trial["loss_matrix"], roles.LOSS)
                self.assertEqual(trial["value"], native[row["request_id"]]["value"])
                self.assertEqual(trial["confidence"], native[row["request_id"]]["confidence"])
            legal = projected["role-evidence-01-baseline"]
            unsafe = projected["role-context-01-baseline"]
            self.assertEqual((legal["loss"], legal["correct"], legal["unsafe"], legal["guard_rejected"]), (.5, False, False, False))
            self.assertEqual((unsafe["loss"], unsafe["correct"], unsafe["unsafe"], unsafe["guard_rejected"]), (1, False, True, True))

    def test_custom_retained_matrix_and_all_failure_outcomes_keep_planned(self):
        manifest = roles.prepare("decisions", replicates=1)
        matrix = {"correct": .05, "wrong_legal": .25, "unsafe": .9, "failure_or_missing": .8}
        for request in manifest["requests"]:
            request["rubric"]["loss_matrix"] = copy.deepcopy(matrix)
        entries = roles.baseline_entries(manifest, "first")
        # A missing request, transport error, refusal, and rubric-defined unknown
        # remain separate native outcomes, all with the retained failure loss.
        missing = entries.pop()["request_id"]
        entries[0] = {"request_id": entries[0]["request_id"], "http_status": 503, "error": "offline fixture"}
        entries[1]["response"]["answers"][0] = {"name": "next", "type": "refusal"}
        unknown_id = entries[2]["request_id"]
        unknown_request = next(r for r in manifest["requests"] if r["id"] == unknown_id)
        unknown_request["rubric"]["questions"]["next"]["unknown_values"] = [entries[2]["response"]["answers"][0]["choice"]]
        reseal_manifest(manifest)
        role_report = roles.evaluate(manifest, entries)
        projected = ledger.from_api(manifest, entries)["trials"]
        self.assertEqual(len(projected), len(manifest["requests"]))
        self.assertEqual({r["outcome"] for r in projected if r["outcome"] != "ok"}, {"missing", "error", "refusal", "unknown"})
        role_rows = {r["request_id"]: r for r in role_report["requests"]}
        for trial in projected:
            expected = role_rows[trial["request_id"]]
            self.assertEqual(trial["loss"], expected["loss"])
            self.assertEqual(trial["outcome"], expected["outcome"])
            self.assertEqual(trial["retained_failure_loss"], .8)
            self.assertEqual(trial["loss_matrix"], matrix)
            if trial["outcome"] != "ok":
                self.assertIsNone(trial["correct"])
                self.assertFalse(expected["correct"])
                self.assertIsNone(trial["semantic_action"])
                self.assertFalse(trial["unsafe"])
                self.assertFalse(trial["guard_rejected"])
        self.assertEqual(next(t for t in projected if t["request_id"] == missing)["outcome"], "missing")
        empty = ledger.from_api(manifest, [])["trials"]
        self.assertTrue(all(r["outcome"] == "missing" and r["correct"] is None and r["loss"] == .8 for r in empty))

    def test_guard_rejection_cannot_earn_native_rubric_correctness(self):
        manifest = roles.prepare("decisions", replicates=1)
        entries = roles.baseline_entries(manifest, "first")
        request = next(r for r in manifest["requests"] if r["id"] == "role-context-01-baseline")
        entry = next(r for r in entries if r["request_id"] == request["id"])
        request["rubric"]["questions"]["next"]["acceptable"] = [entry["response"]["answers"][0]["choice"]]
        reseal_manifest(manifest)
        native = al.evaluate(manifest, [entry])["requests"][0]["questions"][0]
        self.assertTrue(native["correct"])
        trial = next(r for r in ledger.from_api(manifest, [entry])["trials"] if r["request_id"] == request["id"])
        self.assertEqual((trial["correct"], trial["guard_rejected"], trial["unsafe"], trial["loss"]), (False, True, True, 1))

    def test_role_matrix_validation_is_shared_with_role_report(self):
        mutations = (lambda m: m.pop("correct"), lambda m: m.update(extra=0),
                     lambda m: m.update(wrong_legal=True), lambda m: m.update(wrong_legal=-.1),
                     lambda m: m.update(wrong_legal=1.1), lambda m: m.update(wrong_legal=".25"),
                     lambda m: m.update(wrong_legal=float("inf")), lambda m: m.update(wrong_legal=.25))
        for mutation in mutations:
            manifest = roles.prepare("decisions", replicates=1)
            mutation(manifest["requests"][0]["rubric"]["loss_matrix"])
            # Digest serialization intentionally rejects infinity; other invalid
            # retained matrices reach both canonical validation entry points.
            if manifest["requests"][0]["rubric"]["loss_matrix"].get("wrong_legal") == float("inf"):
                self.assertRaises(al.ApiLabError, roles.validate_loss_matrices, manifest["requests"])
                continue
            reseal_manifest(manifest)
            self.assertRaises(al.ApiLabError, roles.evaluate, manifest, [])
            self.assertRaises(al.ApiLabError, ledger.from_api, manifest, [])

    def test_mixed_manifest_projects_role_loss_and_generic_binary_separately(self):
        manifest = prepare_probes("decisions")
        generic_entries = al.oracle_entries(manifest)
        wrong = next(r for r in generic_entries if r["request_id"] == "probe-label")
        answer = wrong["response"]["answers"][0]
        answer["choice"] = "blue"
        answer["probabilities"] = [{"value": value, "probability": float(value == "blue")} for value in ("red", "blue")]
        generic_expected = ledger.from_api(manifest, generic_entries)
        role_manifest = roles.prepare("decisions", replicates=1)
        role_entries = roles.baseline_entries(role_manifest, "first")
        selected_ids = {"role-evidence-01-baseline", "role-context-01-baseline"}
        manifest["requests"].extend(r for r in role_manifest["requests"] if r["id"] in selected_ids)
        # Non-role rubrics do not participate in the role matrix contract.
        manifest["requests"][0]["rubric"]["loss_matrix"] = {"not_a_role_matrix": True}
        reseal_manifest(manifest)
        entries = generic_entries + [r for r in role_entries if r["request_id"] in selected_ids]
        projected = ledger.from_api(manifest, entries)
        role_rows = [r for r in projected["trials"] if r["request_id"] in selected_ids]
        generic_rows = [r for r in projected["trials"] if r["request_id"] not in selected_ids]
        self.assertEqual(generic_rows, generic_expected["trials"])
        self.assertEqual(next(r for r in generic_rows if r["request_id"] == "probe-label")["loss"], 1)
        self.assertTrue(all("retained_failure_loss" not in r for r in generic_rows))
        self.assertEqual(sorted(r["loss"] for r in role_rows), [.5, 1])
        self.assertEqual(len(projected["trials"]), 8)
        self.assertEqual(len(projected["requests"]), 6)

    def test_api_record_load_entry_preserves_role_losses_and_partial_denominator(self):
        manifest = roles.prepare("decisions", replicates=1)
        chosen = {"role-evidence-01-baseline", "role-context-01-baseline"}
        entries = [r for r in roles.baseline_entries(manifest, "first") if r["request_id"] in chosen]
        record = al.build_record(manifest, entries, provenance="synthetic", allow_partial=True)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "record.json"
            path.write_text(json.dumps(record), encoding="utf-8")
            before = path.read_bytes()
            view = ledger.load_ledger(path)
            self.assertEqual(path.read_bytes(), before)
        rows = {r["request_id"]: r for r in view["trials"]}
        self.assertEqual(len(rows), 48)
        self.assertEqual(rows["role-evidence-01-baseline"]["loss"], .5)
        self.assertEqual(rows["role-context-01-baseline"]["loss"], 1)
        self.assertEqual(sum(r["outcome"] == "missing" for r in rows.values()), 46)
        self.assertTrue(all(r["correct"] is None and r["loss"] == 1 for r in rows.values() if r["outcome"] == "missing"))
        self.assertTrue(view["synthetic"])
        self.assertEqual(view["provenance"], "synthetic")

    def test_shared_helper_is_pure_and_native_usage_is_evaluated_once(self):
        manifest = roles.prepare("decisions", replicates=1)
        entries = roles.baseline_entries(manifest, "first")[:2]
        entries[0].update(latency_ms=12, cost={"amount": .2, "currency": "USD"}, usage={"tokens": 7})
        before_manifest, before_entries = copy.deepcopy(manifest), copy.deepcopy(entries)
        with patch.object(al, "evaluate", wraps=al.evaluate) as native_evaluate:
            with patch.object(roles, "evaluate_request", wraps=roles.evaluate_request) as shared:
                view = ledger.from_api(manifest, entries)
        self.assertEqual(native_evaluate.call_count, 1)
        self.assertEqual(shared.call_count, 48)
        self.assertEqual((manifest, entries), (before_manifest, before_entries))
        self.assertEqual(len(view["requests"]), 2)
        self.assertEqual(view["requests"][0]["latency_ms"], 12)
        self.assertEqual(view["requests"][0]["cost"], {"amount": .2, "currency": "USD"})
        self.assertEqual(view["requests"][0]["usage"], {"tokens": 7})
        normalized = al.evaluate(manifest, entries)["requests"][0]
        request = next(r for r in manifest["requests"] if r["id"] == normalized["request_id"])
        retained = copy.deepcopy(normalized)
        result = roles.evaluate_request(request, normalized, manifest["route"])
        result["loss_matrix"]["wrong_legal"] = 0
        result["semantic_action"]["kind"] = "modified-returned-copy"
        self.assertEqual(normalized, retained)
        self.assertEqual(manifest, before_manifest)


if __name__ == "__main__":
    unittest.main()
