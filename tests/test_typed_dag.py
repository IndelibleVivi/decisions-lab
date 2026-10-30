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
            self.assertEqual(
                set(evidence["verification"]),
                {"status", "reason", "locator"},
            )
            self.assertNotIn("gold_synthetic", json.dumps(body))
            self.assertNotIn("matches_gold", json.dumps(body))

    def test_suite_recomputes_authoring_projection_actions(self):
        suite = td.validate_suite(td.build_suite())
        for case in suite["cases"]:
            self.assertEqual(
                set(case["oracle"]["projection_actions"]), set(td.ARMS)
            )
        row = _case(suite, "missing-operand")
        self.assertNotIn("status_evidence", row["oracle"]["gold_fields"])
        self.assertEqual(
            row["oracle"]["projection_actions"]["source-linked"],
            "needs_more_context",
        )

    def test_short_excerpt_binds_only_to_target_current_state(self):
        suite = td.build_suite()
        case = copy.deepcopy(_case(suite, "same-name-entities"))
        case["source"] = "🧪合成来源\n" + case["source"]
        excerpt = "仓库与供应商记录一致"
        values = copy.deepcopy(case["oracle"]["gold_fields"])
        values["status_evidence"] = excerpt

        binding = td._retrieval(
            case, values, None, projection_revision=td.PROJECTION_REVISION
        )
        self.assertTrue(binding["valid"])
        self.assertEqual(binding["quote"], excerpt)
        self.assertEqual(binding["verification"]["status"], "bound")
        self.assertEqual(
            binding["verification"]["reason"],
            "unique_excerpt_in_target_current_state",
        )
        for locator, expected in (
            (binding["link"], excerpt),
            (binding["verification"]["locator"], excerpt),
            (binding["verification"]["target_record_locator"],
             next(line for line in case["source"].splitlines() if line.startswith("目标记录："))),
            (binding["verification"]["current_state_locator"],
             next(line for line in case["source"].splitlines() if line.startswith("目标现行状态："))),
        ):
            self.assertEqual(locator["unit"], "unicode_codepoint")
            self.assertEqual(locator["range"], "half_open")
            self.assertEqual(
                case["source"][locator["start"]:locator["end"]],
                expected,
            )

    def test_downstream_body_only_uses_successfully_bound_short_evidence(self):
        suite = td.build_suite()
        case = _case(suite, "same-name-entities")
        values = copy.deepcopy(case["oracle"]["gold_fields"])
        values["status_evidence"] = "仓库与供应商记录一致"
        binding = td._retrieval(
            case, values, None,
            projection_revision=td.PROJECTION_REVISION,
        )
        calculation = td._calculate(
            case, values, force_gold=False,
            projection_revision=td.PROJECTION_REVISION,
        )
        body = td._projection_body(
            suite, case, "source-linked", values, calculation, binding,
            projection_revision=td.PROJECTION_REVISION,
        )
        self.assertEqual(body["evidence"]["quote"], "仓库与供应商记录一致")
        self.assertEqual(
            body["evidence"]["verification"]["status"], "bound"
        )
        self.assertNotIn("status_evidence", body["fields"])
        self.assertNotIn("gold", json.dumps(body).lower())
        self.assertEqual(
            body["evidence"]["link"]["source"], "provided-task-text"
        )

        rejected = copy.deepcopy(values)
        rejected["status_evidence"] = "供应商当时称第三件损坏"
        rejected_binding = td._retrieval(
            case, rejected, None,
            projection_revision=td.PROJECTION_REVISION,
        )
        rejected_body = td._projection_body(
            suite, case, "source-linked", rejected, calculation,
            rejected_binding,
            projection_revision=td.PROJECTION_REVISION,
        )
        self.assertIsNone(rejected_body["evidence"]["quote"])
        self.assertIsNone(rejected_body["evidence"]["link"])
        self.assertEqual(
            rejected_body["evidence"]["verification"]["status"],
            "rejected",
        )
        self.assertNotIn("status_evidence", rejected_body["fields"])

    def test_bad_short_excerpts_are_rejected_with_explicit_reasons(self):
        suite = td.build_suite()
        case = _case(suite, "current-version-correction")
        rejected = {
            "邻实体": "供应商当时称第三件损坏，争议未解决。",
            "旧版本": "第三件损坏",
            "捏造": "仓库确认全部已验收，无任何争议。",
            "改写": "目标现行状态：仓库复核后确认全部验收，无未解决争议。",
        }
        reasons = {}
        for label, excerpt in rejected.items():
            values = copy.deepcopy(case["oracle"]["gold_fields"])
            values["status_evidence"] = excerpt
            binding = td._retrieval(
                case, values, None,
                projection_revision=td.PROJECTION_REVISION,
            )
            self.assertFalse(binding["valid"], label)
            self.assertEqual(binding["verification"]["status"], "rejected")
            reasons[label] = binding["verification"]["reason"]
        self.assertEqual(reasons["旧版本"], "not_in_current_target_state")
        self.assertEqual(reasons["捏造"], "not_in_current_target_state")
        self.assertEqual(reasons["改写"], "not_in_current_target_state")

        values = copy.deepcopy(case["oracle"]["gold_fields"])
        values["status_evidence"] = "第三件损坏"
        wrong = td._retrieval(
            case, values, None,
            projection_revision=td.PROJECTION_REVISION,
        )
        self.assertEqual(wrong["verification"]["reason"], "not_in_current_target_state")

    def test_wrong_entity_version_duplicate_and_null_are_rejected(self):
        suite = td.build_suite()
        case = _case(suite, "same-name-entities")
        excerpt = "供应商声称全部交付"
        cases = {
            "entity": ("target_entity", "E-201-W", "target_entity_mismatch"),
            "version": ("target_version", "v1", "target_version_mismatch"),
        }
        for label, (field, value, reason) in cases.items():
            values = copy.deepcopy(case["oracle"]["gold_fields"])
            values["status_evidence"] = excerpt
            values[field] = value
            binding = td._retrieval(
                case, values, None,
                projection_revision=td.PROJECTION_REVISION,
            )
            self.assertFalse(binding["valid"], label)
            self.assertEqual(binding["verification"]["reason"], reason)

        values = copy.deepcopy(case["oracle"]["gold_fields"])
        values["status_evidence"] = None
        null_binding = td._retrieval(
            case, values, None,
            projection_revision=td.PROJECTION_REVISION,
        )
        self.assertFalse(null_binding["valid"])
        self.assertEqual(
            null_binding["verification"]["reason"],
            "status_evidence_missing",
        )
        self.assertIsNone(null_binding["quote"])
        self.assertIsNone(null_binding["link"])

        duplicate_line = copy.deepcopy(case)
        duplicate_line["source"] = (
            duplicate_line["source"].replace(
                "\n目标现行状态：三件已经验收，仓库与供应商记录一致，无未解决争议。",
                "",
            )
            + "\n目标现行状态：仓库发现争议未解决，仓库发现争议未解决。"
        )
        values["status_evidence"] = "仓库发现争议未解决"
        duplicate_binding = td._retrieval(
            duplicate_line, values, None,
            projection_revision=td.PROJECTION_REVISION,
        )
        self.assertFalse(duplicate_binding["valid"])
        self.assertEqual(
            duplicate_binding["verification"]["reason"],
            "ambiguous_current_state_excerpt",
        )

        repeated_line = copy.deepcopy(case)
        repeated_line["source"] = (
            repeated_line["source"]
            + "\n目标现行状态：仓库发现争议未解决。"
        )
        values["status_evidence"] = "仓库发现争议未解决"
        repeated_binding = td._retrieval(
            repeated_line, values, None,
            projection_revision=td.PROJECTION_REVISION,
        )
        self.assertFalse(repeated_binding["valid"])
        self.assertEqual(
            repeated_binding["verification"]["reason"],
            "current_target_state_missing_or_ambiguous",
        )

    def test_excerpt_repeated_in_another_entity_is_not_uniquely_bound(self):
        case = copy.deepcopy(_case(td.build_suite(), "current-version-correction"))
        values = copy.deepcopy(case["oracle"]["gold_fields"])
        excerpt = values["status_evidence"].removeprefix("目标现行状态：")
        values["status_evidence"] = excerpt
        case["source"] += "\n邻实体状态：" + excerpt
        binding = td._retrieval(case, values, None, projection_revision=td.PROJECTION_REVISION)
        self.assertFalse(binding["valid"])
        self.assertEqual(binding["verification"]["reason"], "ambiguous_source_excerpt")

    def test_decimal_projection_is_equal_for_gold_and_actual_operands(self):
        case = _case(td.build_suite(), "current-version-correction")
        text_variants = [
            {"quantity": "3", "unit_price": "300.00", "shipping": "50.00"},
            {"quantity": "3.0", "unit_price": "300", "shipping": "50"},
        ]
        projections = []
        for values in text_variants:
            original_extracted = copy.deepcopy(values)
            values["computed_total"] = "990.00"
            calculation = td._calculate(
                case, values, force_gold=False,
                projection_revision=td.PROJECTION_REVISION,
            )
            self.assertEqual(calculation["extracted"], values)
            self.assertEqual(
                calculation["model_total"],
                "990.00",
            )
            values["computed_total"] = original_extracted.get("computed_total")
            projections.append(calculation)
        gold = td._calculate(
            case,
            case["oracle"]["gold_fields"],
            force_gold=True,
            projection_revision=td.PROJECTION_REVISION,
        )
        for calculation in projections + [gold]:
            self.assertEqual(
                calculation["operands"],
                {"quantity": "3", "unit_price": "300", "shipping": "50"},
            )
            self.assertEqual(calculation["total"], "950")
            if calculation["source"] == "decimal_code":
                self.assertEqual(calculation["model_total"], "990.00")
            else:
                self.assertEqual(
                    calculation["extracted"],
                    case["oracle"]["gold_fields"],
                )
        self.assertEqual(
            {json.dumps(item["operands"], sort_keys=True) for item in projections}
            | {json.dumps(gold["operands"], sort_keys=True)},
            {'{"quantity": "3", "shipping": "50", "unit_price": "300"}'},
        )

    def test_equal_decimal_operands_produce_identical_downstream_payload(self):
        suite = td.build_suite()
        actual = td.start(suite, condition="fields-only")
        actual = td.apply_stage(
            actual, td._demo_extraction_source(actual, "oracle")
        )
        gold = td.start(
            suite, condition="fields-only", intervention="calculation"
        )
        gold = td.apply_stage(
            gold, td._demo_extraction_source(gold, "oracle")
        )
        actual_requests = _decision_requests(td.prepare_stage(actual))
        gold_requests = _decision_requests(td.prepare_stage(gold))

        for case_id in (
            "complete-simple", "same-name-entities",
            "current-version-correction", "evidence-link-repair",
        ):
            actual_body = json.loads(
                actual_requests[case_id]["body"]["input"]
            )
            gold_body = json.loads(
                gold_requests[case_id]["body"]["input"]
            )
            self.assertEqual(
                actual_body["calculation"], gold_body["calculation"]
            )

    def test_decimal_projection_preserves_null_and_actual_value(self):
        case = _case(td.build_suite(), "missing-operand")
        calculation = td._calculate(
            case, case["oracle"]["gold_fields"], force_gold=False,
            projection_revision=td.PROJECTION_REVISION,
        )
        self.assertEqual(
            calculation["operands"],
            {"quantity": "2", "unit_price": "400", "shipping": None},
        )
        self.assertIsNone(calculation["total"])
        self.assertFalse(calculation["complete"])
        wrong = copy.deepcopy(case["oracle"]["gold_fields"])
        wrong["quantity"] = "2.0"
        wrong["unit_price"] = "400.00"
        actual = td._calculate(
            case, wrong, force_gold=False,
            projection_revision=td.PROJECTION_REVISION,
        )
        self.assertEqual(actual["operands"], calculation["operands"])
        self.assertEqual(actual["extracted"], wrong)

    def test_projection_revision_v1_and_v2_replay_differently(self):
        suite = td.build_suite()
        current = td.start(suite, condition="source-linked")
        self.assertEqual(current["projection_revision"], td.PROJECTION_REVISION)

        historical = copy.deepcopy(current)
        historical.pop("projection_revision")
        historical["rounds"] = []
        historical = td._seal(historical)
        historical = td.apply_stage(
            historical, td._demo_stage_source(historical, "oracle")
        )
        current = td.apply_stage(
            current, td._demo_stage_source(current, "oracle")
        )
        old_requests = _decision_requests(td.prepare_stage(historical))
        new_requests = _decision_requests(td.prepare_stage(current))
        old_body = json.loads(old_requests["same-name-entities"]["body"]["input"])
        new_body = json.loads(new_requests["same-name-entities"]["body"]["input"])
        self.assertIn("status_evidence", old_body["fields"])
        self.assertNotIn("status_evidence", new_body["fields"])
        self.assertNotIn("verification", old_body["evidence"])
        historical_report = td.report(historical)
        current_report = td.report(current)
        self.assertEqual(
            historical_report["projection_revision"],
            td.HISTORICAL_PROJECTION_REVISION,
        )
        self.assertEqual(
            current_report["projection_revision"],
            td.PROJECTION_REVISION,
        )
        historical_row = next(
            row for row in historical_report["rows"]
            if row["case_id"] == "same-name-entities"
        )
        current_row = next(
            row for row in current_report["rows"]
            if row["case_id"] == "same-name-entities"
        )
        self.assertEqual(
            historical_row["calculation"]["operands"]["unit_price"],
            "300.0",
        )
        self.assertEqual(
            current_row["calculation"]["operands"]["unit_price"],
            "300",
        )
        self.assertNotIn("verification", historical_row["retrieval"])
        self.assertEqual(
            current_row["retrieval"]["verification"]["status"],
            "bound",
        )

        edited = copy.deepcopy(current)
        edited["projection_revision"] = 3
        edited = td._seal(edited)
        with self.assertRaisesRegex(ValueError, "projection_revision"):
            td.report(edited)

        with self.assertRaisesRegex(ValueError, "same projection revision"):
            td.compare(historical, current)

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
