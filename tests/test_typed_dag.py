"""Behavioral tests for the typed extraction -> Decimal -> decision DAG.

These tests intentionally exercise the public workflow boundary. The synthetic
fixtures use retained Clairic collections and native api-lab records;
the parser and retained-record validation are not mocked.
"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from decision_lab import typed_dag as td


def _case(workflow, case_id):
    if "suite" in workflow:
        workflow = workflow["suite"]
    return next(
        case for case in workflow["cases"] if case["id"] == case_id
    )


def _decision_requests(plan):
    return {
        request["trial"]["unit_id"]: request
        for request in plan["requests"]
    }


def _public_input(request):
    body = request["body"]
    return json.loads(body.get("input", body.get("state")))


class TypedDagBehaviorTests(unittest.TestCase):
    def test_actual_extraction_value_changes_downstream_native_body(self):
        base = td.start(td.build_suite(), condition="fields-only")
        extraction_a = td.apply_stage(base, td._demo_stage_source(base, "oracle"))
        extraction_b = td.apply_stage(
            td.start(td.build_suite(), condition="fields-only"),
            td._demo_stage_source(base, "wrong-field"),
        )

        plan_a = td.prepare_stage(extraction_a)
        plan_b = td.prepare_stage(extraction_b)
        self.assertIsNotNone(plan_a)
        self.assertIsNotNone(plan_b)
        self.assertEqual(plan_a["kind"], "api-lab")
        self.assertNotEqual(
            _decision_requests(plan_a)["complete-simple"]["body"],
            _decision_requests(plan_b)["complete-simple"]["body"],
        )
        self.assertNotEqual(
            _public_input(_decision_requests(plan_a)["complete-simple"]),
            _public_input(_decision_requests(plan_b)["complete-simple"]),
        )

    def test_one_extraction_source_can_be_shared_without_duplicate_request_accounting(self):
        suite = td.build_suite()
        fields = td.start(suite, condition="fields-only")
        linked = td.start(suite, condition="source-linked")
        self.assertEqual(td.prepare_stage(fields), td.prepare_stage(linked))
        source = td._demo_stage_source(fields)
        fields = td.apply_stage(fields, source)
        linked = td.apply_stage(linked, source)
        comparison = td.compare(fields, linked)
        self.assertEqual(comparison["shared_extraction_request_count"], len(suite["cases"]))
        self.assertEqual(td.report(fields)["native"]["request_count"], len(suite["cases"]))
        self.assertEqual(td.report(linked)["native"]["request_count"], len(suite["cases"]))
        self.assertEqual(td.report(fields)["native"]["call_count"], 0)
        decision = td._demo_stage_source(fields)
        with self.assertRaises((ValueError, KeyError)):
            td.apply_stage(linked, decision)

    def test_quote_locator_round_trips_unicode_source_without_gold_labels_in_body(self):
        suite = td.build_suite()
        for case in suite["cases"]:
            case["source"] = "🧪合成材料\n" + case["source"]
            case["request"]["state"] = case["source"]
        workflow = td.demo(suite, condition="source-linked", intervention="retrieval")
        for row in td.report(workflow)["rows"]:
            body = row["body"]
            evidence = body["evidence"]
            link = evidence["link"]
            source = _case(suite, row["case_id"])["source"]
            self.assertEqual(link["unit"], "unicode_codepoint")
            self.assertEqual(source[link["start"]:link["end"]], evidence["quote"])
            self.assertNotIn("gold_synthetic", json.dumps(body))
            self.assertNotIn("matches_gold", json.dumps(body))

    def test_extraction_request_excludes_truth_and_uses_typed_contract(self):
        workflow = td.start(td.build_suite())
        plan = td.prepare_stage(workflow)
        self.assertEqual(plan["kind"], "typed-values")
        self.assertEqual(plan["route"], "clairic")
        for request in plan["requests"]:
            body = request["body"]
            self.assertEqual(set(body), {"model", "state", "fields", "options"})
            self.assertNotIn("choices", body)
            rendered = json.dumps(body, ensure_ascii=False)
            for marker in (
                "gold_fields",
                "gold_evidence",
                "optimal_action",
                "projection_actions",
                "failure_loss",
                "editorial_oracle",
            ):
                self.assertNotIn(marker, rendered)

    def test_schema_gap_pair_has_same_fields_but_opposite_optimal_actions(self):
        suite = td.build_suite()
        pair = [
            case for case in suite["cases"]
            if case["source_family"] == "schema-gap-pair"
        ]
        self.assertEqual(len(pair), 2)
        self.assertEqual(
            pair[0]["oracle"]["gold_fields"],
            pair[1]["oracle"]["gold_fields"],
        )
        self.assertEqual(
            {case["oracle"]["optimal_action"] for case in pair},
            {"suggest_continue", "inspect_dispute"},
        )
        self.assertNotIn("status_evidence", pair[0]["fields"])
        self.assertNotIn("status_evidence", pair[1]["fields"])

        workflow = td.start(suite)
        extraction = td.apply_stage(
            workflow, td._demo_stage_source(workflow, "oracle")
        )
        requests = _decision_requests(td.prepare_stage(extraction))
        self.assertEqual(
            requests["schema-gap-continue"]["body"],
            requests["schema-gap-dispute"]["body"],
        )
        pair_demo = td.report(td.demo(suite, condition="fields-only"))
        by_id = {row["case_id"]: row for row in pair_demo["rows"]}
        for case_id in ("schema-gap-continue", "schema-gap-dispute"):
            self.assertEqual(
                by_id[case_id]["attribution"]["schema"],
                "information_missing",
            )
            self.assertEqual(
                by_id[case_id]["attribution"]["extraction"],
                "exact",
            )

    def test_source_linked_retrieval_repairs_schema_gap(self):
        suite = td.build_suite()
        workflow = td.start(suite, condition="source-linked")
        extraction = td.apply_stage(
            workflow, td._demo_stage_source(workflow, "oracle")
        )
        requests = _decision_requests(td.prepare_stage(extraction))
        self.assertEqual(
            requests["schema-gap-continue"]["body"],
            requests["schema-gap-dispute"]["body"],
        )

        repaired_workflow = td.start(
            suite, condition="source-linked", intervention="retrieval"
        )
        repaired_extraction = td.apply_stage(
            repaired_workflow,
            td._demo_stage_source(repaired_workflow, "oracle"),
        )
        repaired_requests = _decision_requests(
            td.prepare_stage(repaired_extraction)
        )
        self.assertNotEqual(
            repaired_requests["schema-gap-continue"]["body"],
            repaired_requests["schema-gap-dispute"]["body"],
        )
        plain = td.report(td.demo(suite, condition="source-linked"))
        repaired = td.report(td.demo(
            suite,
            condition="source-linked",
            intervention="retrieval",
        ))
        plain_by_id = {row["case_id"]: row for row in plain["rows"]}
        repaired_by_id = {row["case_id"]: row for row in repaired["rows"]}
        self.assertEqual(
            plain_by_id["schema-gap-continue"]["attribution"]["retrieval"],
            "evidence_link_error",
        )
        self.assertEqual(
            repaired_by_id["schema-gap-continue"]["attribution"]["retrieval"],
            "exact",
        )
        self.assertEqual(
            repaired_by_id["schema-gap-dispute"]["action"],
            "inspect_dispute",
        )

    def test_null_operand_is_not_imputed(self):
        suite = td.build_suite()
        workflow = td.demo(suite, condition="fields-only")
        result = td.report(workflow)
        row = next(
            row for row in result["rows"]
            if row["case_id"] == "missing-operand"
        )
        self.assertIsNone(row["adopted_fields"]["shipping"])
        self.assertIsNone(row["calculation"]["total"])
        self.assertFalse(row["calculation"]["complete"])
        self.assertEqual(row["attribution"]["calculation"], "missing_operand")
        self.assertEqual(row["action"], "needs_more_context")

    def test_completed_parse_error_remains_terminal_error_and_evidence(self):
        workflow = td.start(td.build_suite(), replicates=2)
        plan = td.prepare_stage(workflow)
        # Force a real collection so the malformed attempt can be retained.
        source = td._demo_extraction_source(workflow, "oracle")
        self.assertEqual(source["schema"], "decisions-lab.collection/1")
        first = source["attempts"][0]
        first.update(
            state="parse_error",
            delivery="response_received",
            http_status=200,
            parse_status="malformed",
            parsed=None,
            raw_body_base64="ew==",
        )
        source = td._seal(source)
        advanced = td.apply_stage(workflow, source)
        result = td.report(advanced)
        row = next(
            row for row in result["rows"]
            if row["case_id"] == plan["requests"][0]["case_id"]
        )
        self.assertEqual(row["extraction_outcome"], "error")
        self.assertEqual(row["decision_outcome"], "error")
        self.assertEqual(row["terminal_loss"], 12.0)
        self.assertTrue(row["terminal"])
        malformed = next(
            item for item in advanced["rounds"][0]["source"]["attempts"]
            if item["request_id"] == plan["requests"][0]["id"]
        )
        self.assertEqual(malformed["state"], "parse_error")
        self.assertEqual(malformed["parse_status"], "malformed")
        self.assertEqual(malformed["raw_body_base64"], "ew==")

    def test_partial_known_and_unknown_accounting_stays_unknown(self):
        workflow = td.start(td.build_suite(), replicates=2)
        source = td._demo_extraction_source(workflow, "oracle")
        self.assertEqual(source["provenance"], "synthetic")
        source.update(provenance="collector", synthetic=False)
        source["endpoint"] = (
            "https://api.cloudflare.com/client/v4/accounts/" + "a" * 32
            + "/ai/run/@cf/cloudflare/clairic"
        )
        source["attempts"][0]["usage"] = {
            "input_tokens": 7,
            "output_tokens": 3,
        }
        source["attempts"][0]["cost"] = {
            "amount": 0.01,
            "currency": "USD",
        }
        source = td._seal(source)
        advanced = td.apply_stage(workflow, source)
        result = td.report(advanced)
        extraction_stage = next(
            item for item in result["native"]["stages"]
            if item["stage"] == "extract"
        )
        self.assertEqual(extraction_stage["request_count"], 14)
        self.assertIsNone(extraction_stage["usage"])
        self.assertIsNone(extraction_stage["cost"])
        self.assertIsNone(result["native"]["usage"])
        self.assertIsNone(result["native"]["cost"])

    def test_replicates_keep_full_denominator_and_one_request_per_decision(self):
        workflow = td.demo(td.build_suite(), replicates=2)
        result = td.report(workflow)
        self.assertEqual(result["planned"], 14)
        self.assertEqual(result["counts"]["planned"], 14)
        self.assertTrue(result["fully_terminal"])
        self.assertEqual(
            result["native"]["stages"][0]["planned_requests"],
            14,
        )
        self.assertEqual(result["native"]["stages"][-1]["request_count"], 14)
        self.assertEqual(result["native"]["request_count"], 28)
        self.assertEqual(
            len({
                (row["id"], row["replicate"]) for row in workflow["planned"]
            }),
            14,
        )

    def test_stale_stage_duplicate_and_tampering_are_rejected_atomically(self):
        workflow = td.start(td.build_suite())
        source = td._demo_extraction_source(workflow, "oracle")
        before = copy.deepcopy(workflow)
        advanced = td.apply_stage(workflow, source)
        self.assertEqual(workflow, before)

        with self.assertRaises(ValueError):
            td.apply_stage(advanced, source)
        incomplete = copy.deepcopy(source)
        incomplete["attempts"].pop()
        td._seal(incomplete)
        with self.assertRaises(ValueError):
            td.apply_stage(workflow, incomplete)
        uncertain = copy.deepcopy(source)
        uncertain["attempts"][0]["delivery"] = "uncertain"
        td._seal(uncertain)
        with self.assertRaises(ValueError):
            td.apply_stage(workflow, uncertain)

        duplicate = copy.deepcopy(source)
        duplicate["attempts"].append(copy.deepcopy(duplicate["attempts"][0]))
        with self.assertRaises(ValueError):
            td.apply_stage(workflow, duplicate)
        self.assertEqual(workflow, before)

        tampered = copy.deepcopy(source)
        tampered["attempts"][0]["parsed"]["answers"]["quantity"]["value"] += 1
        with self.assertRaises(ValueError):
            td.apply_stage(workflow, tampered)
        self.assertEqual(workflow, before)

    def test_replay_rebuilds_report_and_rejects_cached_or_edited_state(self):
        workflow = td.demo(td.build_suite(), condition="source-linked")
        result = td.report(workflow)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "workflow.json"
            path.write_text(
                json.dumps(workflow, ensure_ascii=False),
                encoding="utf-8",
            )
            self.assertEqual(td.report(path), result)

            cached = copy.deepcopy(workflow)
            cached["rows"] = copy.deepcopy(result["rows"])
            with self.assertRaises(ValueError):
                td.report(cached)

            edited = copy.deepcopy(workflow)
            source = edited["rounds"][0]["source"]
            source["attempts"][0]["parsed"]["answers"]["quantity"]["value"] = 99
            with self.assertRaises(ValueError):
                td.report(edited)

    def test_calculation_and_decision_errors_are_distinguished(self):
        case = _case(td.build_suite(), "complete-simple")
        wrong_fields = copy.deepcopy(case["oracle"]["gold_fields"])
        wrong_fields["quantity"] += 1
        good_operands = td._calculate(case, wrong_fields, force_gold=False)
        self.assertTrue(good_operands["complete"])
        self.assertFalse(good_operands["matches_gold"])
        self.assertEqual(
            td._decimal(good_operands["total"], where="total"),
            td._decimal("4", where="q") * td._decimal("350.00", where="p")
            + td._decimal("50.00", where="s"),
        )

        wrong_decision = td.report(
            td.demo(condition="direct", policy="wrong-decision")
        )
        self.assertTrue(all(
            row["attribution"]["decision"] == "decision_error"
            for row in wrong_decision["rows"]
        ))

    def test_compare_does_not_call_conditional_loss_a_complete_total(self):
        suite = td.build_suite()
        direct = td.demo(suite, condition="direct", replicates=2)
        fields_start = td.start(suite, condition="fields-only", replicates=2)
        extraction = td.apply_stage(
            fields_start, td._demo_stage_source(fields_start, "oracle")
        )
        fields = extraction
        compared = td.compare(direct, fields)
        self.assertEqual(compared["summary"]["planned"], 14)
        self.assertEqual(compared["summary"]["right_missing"], 14)
        self.assertIsNone(compared["summary"]["right_loss_total"])
        self.assertIsNone(compared["summary"]["paired_delta_total"])
        self.assertIs(compared["summary"]["complete"], False)
        self.assertIn("conditional_observed_pairs", compared["summary"])
        self.assertIsNone(compared["interval"])


if __name__ == "__main__":
    unittest.main()
