"""Finite sufficiency witnesses, source observations and native E2 integration."""
import copy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from decision_lab import api_lab as al, evidence, evidence_workflow as ew, schema_inquiry as si, studio
from decision_lab.cli import main


class SchemaInquiryTests(unittest.TestCase):
    def test_witness_and_repair_are_task_relative_and_unavailable_is_not_repaired(self):
        design = si.build_design()
        result = si.audit_design(design)
        self.assertEqual(result["insufficient_groups"], 3)
        by_family = {g["source_family"]: g for g in result["groups"]}
        collision = by_family["current-policy"]
        self.assertEqual(collision["minimal_repairs"], [["current_policy"]])
        a, b = collision["witness"]
        self.assertNotEqual(a["source"], b["source"])
        self.assertEqual({k: a["values"][k] for k in design["fields"]}, collision["projection"])
        self.assertEqual({k: b["values"][k] for k in design["fields"]}, collision["projection"])
        self.assertFalse(set(a["optimal_actions"]) & set(b["optimal_actions"]))
        self.assertEqual(by_family["unavailable"]["minimal_repairs"], [])
        self.assertTrue(by_family["already-sufficient"]["sufficient"])
        design["fields"].append("current_policy")
        fixed = si.audit_design(design)
        self.assertEqual(fixed["insufficient_groups"], 1)
        self.assertEqual(next(g for g in fixed["groups"] if not g["sufficient"])["source_family"], "unavailable")

    def test_pairwise_overlap_is_not_a_common_action_and_witness_is_minimal(self):
        rows = [{"id": str(i), "source_family": "f", "values": {"visible": 0, "detail": i},
                 "optimal_actions": actions} for i, actions in enumerate((["a", "b"], ["b", "c"], ["a", "c"]))]
        result = si.audit(rows, ["visible"])
        self.assertFalse(result["sufficient"])
        self.assertEqual(len(result["groups"][0]["witness"]), 3)
        self.assertEqual(result["minimal_repairs"], [["detail"]])
        self.assertTrue(si.audit(rows[:2], ["visible"])["sufficient"])

    def test_queries_are_real_document_locators_without_offset_side_channels(self):
        suite = si.compile_suite(si.build_design())
        for scenario in suite["scenarios"]:
            if scenario["source_family"] != "already-sufficient":
                # Archive content/positions must not accidentally reveal a current clause.
                self.assertEqual(len({h["observations"]["archive"] for h in scenario["hypotheses"]}), 1)
            if scenario["source_family"] == "unavailable":
                self.assertEqual(len({h["observations"]["current"] for h in scenario["hypotheses"]}), 1)
        report = ew.report(ew.demo(suite))
        for row in report["episodes"]:
            inspector = row["schema_evidence"]
            for step in inspector["steps"]:
                chosen = step["chosen"]
                if "observation" in chosen:
                    observed = json.loads(chosen["observation"])
                    locator = observed["locator"]
                    text = inspector["source_documents"][locator["source"]]
                    self.assertEqual(text[locator["start"]:locator["end"]], observed["quote"])

    def test_native_body_does_not_publish_actual_world_or_witness(self):
        suite = si.compile_suite(si.build_design())
        workflow = ew.start(suite, route="decisions", replicates=2)
        manifest = ew.prepare_round(workflow)
        self.assertEqual(len(manifest["requests"]), 16)
        bodies = [r["body"] for r in manifest["requests"]]
        encoded = json.dumps(bodies)
        for forbidden in ("world_id", "optimal_actions", "schema_design", "witness", "source_documents"):
            self.assertNotIn(forbidden, encoded)
        # Both hidden worlds with identical fields see byte-identical initial input.
        inputs = [r["body"]["input"] for r in manifest["requests"]]
        self.assertEqual(len(set(inputs)), 4)
        self.assertEqual(ew.report(workflow)["summary"]["missing"], 16)

    def test_shared_e2_policies_and_full_denominators(self):
        suite = si.compile_suite(si.build_design())
        with patch("socket.socket", side_effect=AssertionError("offline only")):
            outputs = {p: ew.demo(suite, policy=p) for p in ("stop", "checklist", "optimal")}
        reports = {p: ew.report(w) for p, w in outputs.items()}
        self.assertEqual([reports[p]["summary"]["total_loss"] for p in outputs], [18, 22, 10])
        self.assertEqual(reports["optimal"]["summary"]["query_count"], 4)
        for row in reports["optimal"]["episodes"]:
            if row["source_family"] in ("unavailable", "already-sufficient"):
                self.assertEqual(row["query_count"], 0)
        comparison = ew.compare(outputs["stop"], outputs["optimal"])
        self.assertEqual(comparison["summary"]["planned"], 8)
        self.assertEqual(comparison["summary"]["fully_observed_pairs"], 8)
        self.assertTrue(comparison["evidence"]["right"]["synthetic"])

    def test_api_failure_is_not_business_abstain_and_missing_stays_pending(self):
        workflow = ew.start(si.compile_suite(si.build_design()), route="decisions")
        manifest = ew.prepare_round(workflow)
        with self.assertRaisesRegex(ValueError, "missing|nonempty"):
            ew.apply_round(workflow, al.build_record(manifest, [], provenance="imported", allow_partial=True))
        self.assertEqual(workflow["rounds"], [])
        entries = [{"request_id": r["id"], "http_status": 500, "error": "http_error"} for r in manifest["requests"]]
        result = ew.report(ew.apply_round(workflow, al.build_record(manifest, entries, provenance="imported")))
        self.assertEqual(result["summary"]["api_failed"], 8)
        self.assertEqual(result["summary"]["abstained"], 0)
        self.assertEqual(result["summary"]["total_loss"], 96)

    def test_full_text_control_charges_all_reads_but_has_one_native_decision(self):
        suite = si.compile_suite(si.build_design())
        initial = ew.start(suite, route="decisions", query_mode="read-all")
        bodies = [json.loads(r["body"]["input"]) for r in ew.prepare_round(initial)["requests"]]
        self.assertTrue(all("source_text" in b and len(b["history"]) == 2 for b in bodies))
        self.assertTrue(all(not a.startswith("query:") for b in bodies for a in b["available_actions"]))
        report = ew.report(ew.demo(suite, query_mode="read-all"))
        self.assertEqual(report["native"]["request_count"], 8)
        self.assertEqual(report["summary"]["query_count"], 16)
        self.assertEqual(report["summary"]["query_cost"], 16)
        self.assertEqual(report["summary"]["total_loss"], 22)
        self.assertEqual(report["native"]["turns"], 1)
        self.assertTrue(all(row["schema_evidence"]["source_visible_to_model"] for row in report["episodes"]))
        self.assertFalse(ew.report(ew.demo(suite))["episodes"][0]["schema_evidence"]["source_visible_to_model"])
        self.assertEqual(ew.compare(ew.demo(suite), ew.demo(suite, query_mode="read-all"))["summary"]["planned"], 8)
        adaptive = ew.start(suite, route="decisions")
        with self.assertRaisesRegex(ValueError, "query_mode"):
            studio.bind_import(adaptive, adaptive, ew.demo(suite, query_mode="read-all"))

    def test_cached_compilation_and_invalid_fields_are_rejected(self):
        design = si.build_design()
        design["fields"] = ["oracle"]
        with self.assertRaisesRegex(ValueError, "schema fields"):
            si.compile_suite(design)
        suite = si.compile_suite(si.build_design())
        suite["scenarios"][0]["description"] = "forged cached projection"
        with self.assertRaisesRegex(ValueError, "differs"):
            ew.start(suite, route="decisions")
        rows = si.finite_rows(si.build_design())
        with self.assertRaisesRegex(ValueError, "duplicate"):
            si.audit(rows + [rows[0]], ["entity"])

    def test_unavailable_single_document_cannot_leak_as_archive(self):
        design = si.build_design()
        design["families"] = [design["families"][2]]
        design["fields"] = ["archive_policy"]
        for case in design["families"][0]["cases"]:
            case["world"]["documents"] = [max(case["world"]["documents"], key=lambda d: d["version"])]
        with self.assertRaisesRegex(ValueError, "distinct archive"):
            si.compile_suite(design)

    def test_studio_freeze_reopen_reproduce_and_changed_schema_fork(self):
        with tempfile.TemporaryDirectory() as root:
            store = studio.Store(root)
            s = store.command("create", {"kind": "schema-inquiry"})
            def act(action, **data):
                nonlocal s
                s = store.command(action, {"id": s["id"], "revision": s["revision"], **data})
            preview = store.command("audit-schema", {"design": s["definition"]["schema_design"]})
            self.assertEqual(preview["insufficient_groups"], 3)
            act("freeze"); act("run")
            original = copy.deepcopy(s)
            act("reproduce", analysis=s["analyses"][-1]["id"])
            self.assertTrue(s["analyses"][-1]["diff"]["equal"])
            imported = store.command("import-bundle", {"bundle": store.export(s["id"])})
            self.assertEqual(imported["analyses"][-1]["result"], s["analyses"][-1]["result"])
            act("fork")
            definition = copy.deepcopy(s["definition"])
            definition["schema_design"]["fields"].append("current_policy")
            act("save", definition=definition); act("freeze"); act("run")
            report = s["analyses"][-1]["result"]["conditions"]["optimal"]["report"]
            self.assertEqual(report["schema_audit"]["insufficient_groups"], 1)
            self.assertEqual(report["summary"]["query_count"], 0)
            self.assertEqual(store.get(original["id"])["definition"], original["definition"])

    def test_cli_design_to_native_rounds(self):
        def command(*args):
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                status = main(["research", *args])
            self.assertEqual((status, err.getvalue()), (0, ""))
            return out.getvalue()
        with tempfile.TemporaryDirectory() as root:
            design, suite, run = [str(Path(root) / (n + ".json")) for n in ("design", "suite", "run")]
            command("schema-design", "--output", design)
            self.assertEqual(json.loads(command("schema-audit", design))["insufficient_groups"], 3)
            command("schema-suite", design, "--output", suite)
            command("evidence-demo", "--suite", suite, "--output", run)
            self.assertEqual(json.loads(command("evidence-report", run))["summary"]["missing"], 0)
            self.assertEqual(command("evidence-prepare", run).strip(), "null")


if __name__ == "__main__":
    unittest.main()
