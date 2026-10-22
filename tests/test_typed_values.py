"""Typed-values CLI and integrity tests; all offline."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from decision_lab import typed_values as tv
from decision_lab.cli import main

REPO = Path(__file__).resolve().parent.parent
SUITE = REPO / "experiments" / "typed-values" / "examples.json"


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


def _oracle_entries(suite: tv.TypedSuite) -> list[tv.ResponseEntry]:
    entries = []
    for case in suite.cases:
        values = case.editorial_oracle.get("values", {})
        answers = {}
        for name, config in case.fields.items():
            if name == "completion_days":
                upper = float(config["max"])
                value = min(8, upper)
                answers[name] = {
                    "type": config["type"],
                    "value": value,
                    "median": value,
                    "p10": 2.0,
                    "p90": value,
                }
                continue
            elif config["type"] == "number" and isinstance(values.get(name), str):
                value = float(values[name])
            else:
                value = values.get(name)
            answers[name] = {"type": config["type"], "value": value}
        entries.append(
            tv.ResponseEntry(
                experiment_id=case.experiment_id,
                case_id=case.case_id,
                raw={
                    "model": "clairic",
                    "answers": answers,
                    "truncated": False,
                    "usage": {"input_tokens": 1, "output_tokens": 0},
                },
                value_source="native",
            )
        )
    return entries

def _native_raw(answers: dict, **extra) -> dict:
    return {
        "model": "clairic",
        "answers": answers,
        "truncated": False,
        "usage": {"input_tokens": 1, "output_tokens": 0},
        **extra,
    }

def _native_entry(case: tv.TypedCase, answers: dict, **extra) -> tv.ResponseEntry:
    return tv.ResponseEntry(
        experiment_id=case.experiment_id,
        case_id=case.case_id,
        raw=_native_raw(answers, **extra),
        http_status=200,
        value_source="native",
    )


def _write_responses(path: Path, entries: list[tv.ResponseEntry]) -> Path:
    data = {
        "schema": tv.RESPONSE_INPUT_VERSION,
        "provenance": "import",
        "responses": [
            {
                "experiment_id": entry.experiment_id,
                "case_id": entry.case_id,
                "http_status": 200,
                "value_source": "native",
                "response": {"result": entry.raw},
            }
            for entry in entries
        ],
    }
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


class TestSuiteAndPrepare(unittest.TestCase):
    def test_real_suite_has_expected_shape(self):
        suite = tv.load_suite(SUITE)
        self.assertEqual(len(suite.experiments), 3)
        self.assertEqual(len(suite.cases), 7)
        self.assertEqual(len({case.source_group for case in suite.cases}), 3)

    def test_eighth_valid_case_is_loaded_without_fixture_count_coupling(self):
        data = json.loads(SUITE.read_text(encoding="utf-8"))
        extra = json.loads(json.dumps(data["experiments"][0]["cases"][0]))
        extra["id"] = "source-missing-extra"
        data["experiments"][0]["cases"].append(extra)
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "eight-cases.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            suite = tv.load_suite(path)
        self.assertEqual(len(suite.cases), 8)
        self.assertEqual(suite.by_id()["source-missing-extra"].experiment_id,
                         "source-null-identity")

    def test_unknown_experiment_type_is_not_reported_as_supported(self):
        data = json.loads(SUITE.read_text(encoding="utf-8"))
        data["experiments"].append({"id": "unsupported-extra", "cases": [
            json.loads(json.dumps(data["experiments"][0]["cases"][0]))
        ]})
        data["experiments"][-1]["cases"][0]["id"] = "unsupported-case"
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "unsupported.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(tv.TypedValuesError) as raised:
                tv.load_suite(path)
        self.assertIn("unsupported experiment type", str(raised.exception))

    def test_empty_experiment_list_is_rejected(self):
        data = json.loads(SUITE.read_text(encoding="utf-8"))
        data["experiments"] = []
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "empty.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(tv.TypedValuesError) as raised:
                tv.load_suite(path)
        self.assertIn("experiments must be a non-empty array", str(raised.exception))

    def test_prepare_exports_no_editorial_or_label_data(self):
        code, out, _ = _run(["typed-values", "prepare", "--limit", "1"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(len(payload["requests"]), 1)
        request = payload["requests"][0]
        self.assertEqual(set(request), {"experiment_id", "case_id", "request"})
        serialized = json.dumps(payload, ensure_ascii=False)
        for marker in (
            "editorial_oracle",
            "diagnostic_examples",
            "source_group",
            "rationale",
            "span_offsets",
            "expected_decision",
            "elapsed_calendar_days",
        ):
            self.assertNotIn(marker, serialized)
        self.assertEqual(
            set(request["request"]), {"model", "state", "fields", "options"}
        )

    def test_filter_by_experiment_and_case(self):
        code, out, _ = _run(
            [
                "typed-values",
                "prepare",
                "--experiment",
                "estimate-intervals",
                "--case-id",
                "interval-narrow-support",
            ]
        )
        self.assertEqual(code, 0)
        requests = json.loads(out)["requests"]
        self.assertEqual([row["case_id"] for row in requests], ["interval-narrow-support"])
        with self.assertRaises(tv.TypedValuesError):
            tv.select_cases(
                tv.load_suite(SUITE),
                experiment_id="source-null-identity",
                case_ids=["amount-clear"],
            )


class TestOfflineRecordsAndImport(unittest.TestCase):
    def test_baseline_and_demo_write_and_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for command in ("baseline-run", "demo"):
                run = root / command
                code, _, err = _run(
                    ["typed-values", command, "--run-dir", str(run)]
                )
                self.assertEqual(code, 0, err)
                record = run / "typed-values-record.json"
                payload = json.loads(record.read_text(encoding="utf-8"))
                self.assertFalse(payload["live_verified"])
                self.assertEqual(payload["provenance"], command.replace("-run", ""))
                code, out, err = _run(["typed-values", "replay", str(run)])
                self.assertEqual(code, 0, err)
                report = json.loads(out)
                self.assertEqual(report["evaluation"]["counts"]["total"], 7)
                fields = report["evaluation"]["source_fields"]
                self.assertEqual(fields["expected_null"], 2)
                self.assertEqual(fields["spurious_fill_rate"], 0)
                self.assertEqual(fields["missed_present_rate"], 0)
                path_counts = report["evaluation"]["compute_paths"]["direct"]
                self.assertEqual(path_counts["imported_cases"], 0)
                self.assertEqual(path_counts["not_provided"], 2)
                if command == "baseline-run":
                    self.assertEqual(report["evaluation"]["counts"]["error"], 0)
                    self.assertEqual(
                        report["cases"][6]["evaluation"]["kind"],
                        "empirical_history_baseline",
                    )
                    self.assertFalse(
                        report["cases"][6]["evaluation"]["history_baseline"][
                            "within_requested_range"
                        ]
                    )

    def test_import_oracle_responses_end_to_end(self):
        suite = tv.load_suite(SUITE)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            responses = _write_responses(
                root / "responses.json", _oracle_entries(suite)
            )
            run = root / "imported"
            code, _, err = _run(
                [
                    "typed-values",
                    "import",
                    "--responses",
                    str(responses),
                    "--run-dir",
                    str(run),
                ]
            )
            self.assertEqual(code, 0, err)
            data = json.loads(
                (run / "typed-values-record.json").read_text(encoding="utf-8")
            )
            self.assertEqual(data["provenance"], "import")
            self.assertFalse(data["synthetic"])
            self.assertFalse(data["live_verified"])
            code, out, err = _run(["typed-values", "replay", str(run)])
            self.assertEqual(code, 0, err)
            report = json.loads(out)
            self.assertEqual(report["provenance"], "import")
            self.assertEqual(report["evaluation"]["counts"]["ok"], 7)

    def test_import_allows_explicit_unknown_refusal_and_error(self):
        suite = tv.load_suite(SUITE)
        cases = tv.select_cases(suite, case_ids=["source-missing"])
        entries = [
            tv.ResponseEntry(
                experiment_id=cases[0].experiment_id,
                case_id=cases[0].case_id,
                outcome_hint=tv.OUTCOME_UNKNOWN,
                error_detail="provider explicitly selected unknown",
            )
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            response_path = root / "responses.json"
            response_path.write_text(
                json.dumps(
                    {
                        "schema": tv.RESPONSE_INPUT_VERSION,
                        "provenance": "import",
                        "responses": [
                            {
                                "experiment_id": entries[0].experiment_id,
                                "case_id": entries[0].case_id,
                                "kind": tv.OUTCOME_UNKNOWN,
                                "detail": entries[0].error_detail,
                                "value_source": "synthetic",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            code, _, err = _run(
                [
                    "typed-values",
                    "import",
                    "--responses",
                    str(response_path),
                    "--case-id",
                    cases[0].case_id,
                    "--run-dir",
                    str(root / "run"),
                ]
            )
            self.assertEqual(code, 0, err)
            report = json.loads(
                (root / "run" / "typed-values-record.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(report["results"][0]["outcome"], tv.OUTCOME_UNKNOWN)
            self.assertEqual(report["results"][0]["value_source"], "synthetic")

    def test_import_downstream_decisions_are_scored_not_generated(self):
        suite = tv.load_suite(SUITE)
        case = suite.by_id()["amount-disputed"]
        answers = _oracle_entries(suite)[3].raw["answers"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            response_path = root / "responses.json"
            response_path.write_text(
                json.dumps(
                    {
                        "schema": tv.RESPONSE_INPUT_VERSION,
                        "provenance": "import",
                        "responses": [
                            {
                                "experiment_id": case.experiment_id,
                                "case_id": case.case_id,
                                "http_status": 200,
                                "value_source": "native",
                                "response": {"result": _native_raw(answers)},
                "downstream_decisions": {
                    "direct": "inspect_dispute",
                    "extracted_only": "suggest_continue",
                    "source_linked": "needs_more_context",
                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            code, _, err = _run(
                [
                    "typed-values",
                    "import",
                    "--responses",
                    str(response_path),
                    "--case-id",
                    case.case_id,
                    "--run-dir",
                    str(root / "run"),
                ]
            )
            self.assertEqual(code, 0, err)
            row = json.loads(
                (root / "run" / "typed-values-record.json").read_text(
                    encoding="utf-8"
                )
            )["results"][0]["evaluation"]["paths"]
            self.assertEqual(row["direct"]["action_source"], "import")
            self.assertEqual(row["direct"]["action"], "inspect_dispute")
            self.assertTrue(row["direct"]["honest_under_input"])
            self.assertTrue(row["direct"]["full_task_completed"])
            self.assertFalse(row["source_linked"]["honest_under_input"])
            self.assertFalse(row["source_linked"]["full_task_completed"])
            self.assertFalse(row["extracted_only"]["honest_under_input"])
            self.assertFalse(row["extracted_only"]["full_task_completed"])
            self.assertEqual(
                row["source_linked"]["rule_baseline_action"], "inspect_dispute"
            )

    def test_refuse_nonempty_and_source_tree_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            occupied = Path(directory) / "run"
            occupied.mkdir()
            (occupied / "keep").write_text("x", encoding="utf-8")
            code, _, err = _run(
                ["typed-values", "demo", "--run-dir", str(occupied)]
            )
            self.assertEqual(code, 1)
            self.assertIn("not empty", err)
        with self.assertRaises(tv.TypedValuesError):
            tv.write_record(REPO / "experiments" / "typed-values" / "run", {})


class TestStrictEvaluation(unittest.TestCase):
    def setUp(self):
        self.suite = tv.load_suite(SUITE)

    def _make(self, case_id: str, answers: dict):
        case = self.suite.by_id()[case_id]
        entry = tv.ResponseEntry(
            experiment_id=case.experiment_id,
            case_id=case_id,
            raw={"answers": answers},
        )
        return tv.make_result(self.suite, case, entry, span_convention=None)

    def _source_answers(self, value):
        return {
            "current_order_id": {"type": "text", "value": "PO-842"},
            "current_recipient": {"type": "text", "value": "林遥"},
            "current_delivery_date": {"type": "date", "value": value},
            "current_delivery_evidence": {"type": "text", "value": value},
        }

    def test_explicit_null_is_not_missing_field(self):
        result = self._make("source-missing", self._source_answers(None))
        self.assertEqual(result["outcome"], tv.OUTCOME_OK)
        field = result["evaluation"]["fields"]["current_delivery_date"]
        self.assertTrue(field["present"])
        self.assertEqual(field["value_kind"], "null")
        self.assertIsNone(field["value"])

        missing = self._source_answers(None)
        del missing["current_delivery_date"]
        malformed = self._make("source-missing", missing)
        self.assertEqual(malformed["outcome"], tv.OUTCOME_ERROR)
        self.assertIn("current_delivery_date", malformed["error_detail"])
        self.assertEqual(malformed["error_kind"], "response_contract")

    def test_honesty_uses_actual_projection_instead_of_complete_input_oracle(self):
        case = self.suite.by_id()["amount-disputed"]
        entry = _oracle_entries(self.suite)[3]
        entry.raw["answers"]["quantity"]["value"] = None
        entry.downstream_decisions = {"source_linked": "needs_more_context"}
        result = tv.make_result(self.suite, case, entry, span_convention=None)
        paths = result["evaluation"]["paths"]
        self.assertEqual(paths["direct"]["action"], "inspect_dispute")
        linked = paths["source_linked"]
        self.assertTrue(linked["honest_under_input"])
        self.assertFalse(linked["full_task_completed"])
        self.assertNotIn("数量", linked["input"]["source_passage"])

    def test_numeric_equivalence_and_over_limit_do_not_invent_a_dispute(self):
        case = self.suite.by_id()["amount-clear"]
        entry = _oracle_entries(self.suite)[4]
        entry.raw["answers"]["quantity"]["value"] = 3.0
        result = tv.make_result(self.suite, case, entry, span_convention=None)
        self.assertEqual(result["outcome"], tv.OUTCOME_OK)
        self.assertTrue(result["evaluation"]["source_fields"]["fields"]["unit_price"]["exact_match"])
        entry.raw["answers"]["quantity"]["value"] = 4
        result = tv.make_result(self.suite, case, entry, span_convention=None)
        paths = result["evaluation"]["paths"]
        self.assertEqual(paths["direct"]["action"], "suggest_continue")
        self.assertEqual(paths["source_linked"]["action"], "unknown")

    def test_opaque_optional_quantiles_are_retained_without_interpretation(self):
        case = self.suite.by_id()["interval-wide-support"]
        entry = _oracle_entries(self.suite)[5]
        quantiles = [{"vendor_layout_unverified": [1, 2]}]
        entry.raw["answers"]["completion_days"]["quantiles"] = quantiles
        result = tv.make_result(self.suite, case, entry, span_convention=None)
        self.assertEqual(result["outcome"], tv.OUTCOME_OK)
        self.assertEqual(result["raw"]["answers"]["completion_days"]["quantiles"], quantiles)
        self.assertEqual(result["evaluation"]["estimate"]["p90"], 8)

    def test_native_span_shape_is_checked_before_choosing_offset_convention(self):
        case = self.suite.by_id()["source-present"]
        answers = self._source_answers("2026-10-23")
        answers["current_order_id"]["span"] = [True, "invalid"]
        result = tv.make_result(
            self.suite, case, _native_entry(case, answers), span_convention=None
        )
        self.assertEqual(result["outcome"], tv.OUTCOME_ERROR)

    def test_native_value_bounds_are_checked_independently_of_median(self):
        case = self.suite.by_id()["interval-wide-support"]
        entry = _oracle_entries(self.suite)[5]
        entry.raw["answers"]["completion_days"]["value"] = 100
        result = tv.make_result(self.suite, case, entry, span_convention=None)
        self.assertEqual(result["outcome"], tv.OUTCOME_ERROR)

    def test_overflow_json_number_is_rejected_before_record_creation(self):
        with tempfile.TemporaryDirectory() as root:
            response = Path(root) / "overflow.json"
            response.write_text('{"number": 1e999}', encoding="utf-8")
            code, _, err = _run([
                "typed-values", "import", "--responses", str(response),
                "--run-dir", str(Path(root) / "output"),
            ])
            self.assertEqual(code, 1)
            self.assertIn("finite", err)
            self.assertFalse((Path(root) / "output").exists())

    def test_guess_is_preserved_not_promoted(self):
        answers = self._source_answers(None)
        answers["current_delivery_date"]["guess"] = "2026-10-18"
        answers["current_delivery_date"]["confidence"] = 0.99
        answers["current_delivery_date"]["p_null"] = 1
        result = self._make("source-missing", answers)
        field = result["evaluation"]["fields"]["current_delivery_date"]
        self.assertIsNone(field["value"])
        self.assertEqual(field["guess"], "2026-10-18")
        self.assertEqual(field["confidence"], 0.99)
        self.assertEqual(field["p_null"], 1)
        self.assertTrue(result["evaluation"]["fields"]["current_recipient"]["text_match"])

    def test_wrong_entity_fails_relation_but_can_pass_text_existence(self):
        answers = self._source_answers(None)
        answers["current_recipient"] = {"type": "text", "value": "周岚"}
        answers["current_delivery_date"] = {"type": "date", "value": "2026-10-18"}
        result = self._make("source-missing", answers)
        recipient = result["evaluation"]["fields"]["current_recipient"]
        self.assertTrue(recipient["text_match"])
        self.assertFalse(recipient["in_target_scope"])
        self.assertFalse(recipient["entity_version_correct"])
        wrong_evidence = self._source_answers(None)
        wrong_evidence["current_delivery_evidence"] = {
            "type": "text",
            "value": "2026-10-18",
        }
        evidence = self._make("source-missing", wrong_evidence)["evaluation"]["fields"][
            "current_delivery_evidence"
        ]
        self.assertTrue(evidence["text_match"])
        self.assertFalse(evidence["in_target_scope"])
        self.assertFalse(evidence["entity_version_correct"])
        delivery = result["evaluation"]["fields"]["current_delivery_date"]
        self.assertFalse(delivery["exact_match"])

    def test_bool_nonfinite_and_invalid_date_as_numbers_or_dates_rejected(self):
        for bad in (True, "3", float("nan"), float("inf")):
            answers = self._source_answers(None)
            answers["current_delivery_date"] = {"type": "date", "value": "2026-02-30"}
            if isinstance(bad, float):
                answers["current_delivery_date"] = {"type": "date", "value": None}
                answers["current_delivery_evidence"] = {
                    "type": "text",
                    "value": "x",
                }
                entry = tv.ResponseEntry(
                    "source-null-identity",
                    "source-missing",
                    raw={
                        "answers": {
                            **answers,
                            "current_order_id": {"type": "text", "value": "PO-842"},
                        }
                    },
                )
                # Non-finite JSON literals cannot be imported from a file; the
                # internal guard is tested separately below.
                self.assertFalse(tv._finite_number(bad))
                continue
            result = self._make("source-missing", answers)
            self.assertEqual(result["outcome"], tv.OUTCOME_ERROR)

    def test_wrong_answer_type_and_unknown_field_rejected(self):
        answers = self._source_answers(None)
        answers["current_delivery_date"]["type"] = "text"
        self.assertEqual(
            self._make("source-missing", answers)["outcome"], tv.OUTCOME_ERROR
        )

    def test_response_with_local_metadata_is_not_treated_as_answer(self):
        case = self.suite.by_id()["source-missing"]
        result = tv.make_result(
            self.suite,
            case,
            tv.ResponseEntry(
                experiment_id=case.experiment_id,
                case_id=case.case_id,
                raw={
                    "answers": {
                        "current_order_id": {"type": "text", "value": "PO-842"},
                        "current_recipient": {"type": "text", "value": "林遥"},
                        "current_delivery_date": {"type": "date", "value": None},
                        "current_delivery_evidence": {"type": "text", "value": None},
                    },
                    "source_group": "leaked-label",
                },
            ),
            span_convention=None,
        )
        self.assertEqual(result["outcome"], tv.OUTCOME_ERROR)
        self.assertIn("local metadata", result["error_detail"])
        answers = self._source_answers(None)
        answers["extra"] = {"type": "text", "value": "x"}
        self.assertEqual(
            self._make("source-missing", answers)["outcome"], tv.OUTCOME_ERROR
        )

    def test_quantity_null_is_normal_field_and_direct_remains_independent(self):
        entry = _oracle_entries(self.suite)[3]
        answers = dict(entry.raw["answers"])
        answers["quantity"] = {"type": "number", "value": None}
        case = self.suite.by_id()["amount-disputed"]
        result = tv.make_result(
            self.suite, case, _native_entry(case, answers), span_convention=None
        )
        self.assertEqual(result["outcome"], tv.OUTCOME_OK)
        quantity = result["evaluation"]["source_fields"]["fields"]["quantity"]
        self.assertTrue(quantity["present"])
        self.assertEqual(quantity["value_kind"], "null")
        decimal = result["evaluation"]["decimal"]
        self.assertIsNone(decimal["code_total"])
        self.assertFalse(decimal["operands_available"])
        paths = result["evaluation"]["paths"]
        self.assertEqual(paths["direct"]["rule_baseline_action"], "inspect_dispute")
        self.assertEqual(
            paths["extracted_only"]["rule_baseline_action"],
            "needs_more_context",
        )
        self.assertEqual(
            paths["source_linked"]["rule_baseline_action"],
            "needs_more_context",
        )
        self.assertEqual(paths["extracted_only"]["input"]["unit_price"], "350.0")
        self.assertEqual(paths["extracted_only"]["input"]["shipping"], "50.0")

    def test_estimate_null_is_visible_but_not_evaluable(self):
        case = self.suite.by_id()["interval-wide-support"]
        result = tv.make_result(
            self.suite,
            case,
            _native_entry(
                case,
                {
                    "completion_days": {
                        "type": "estimate",
                        "value": None,
                        "median": 4.5,
                        "p10": 2,
                        "p90": 8,
                    }
                },
            ),
            span_convention=None,
        )
        self.assertEqual(result["outcome"], tv.OUTCOME_OK)
        evaluation = result["evaluation"]
        self.assertEqual(evaluation["estimate"]["status"], "null")
        self.assertIsNone(evaluation["estimate"]["median"])
        self.assertEqual(evaluation["observation"]["status"], "not_evaluable")
        self.assertIsNone(evaluation["observation"]["interval_hit"])

    def test_compute_paths_show_same_numbers_different_outcomes(self):
        oracle = self.suite.by_id()
        disputed = self._make(
            "amount-disputed",
            {
                name: {
                    "type": config["type"],
                    "value": (
                        float(value)
                        if config["type"] == "number" and isinstance(value, str)
                        else value
                    ),
                }
                for name, config in oracle["amount-disputed"].fields.items()
                for value in [
                    oracle["amount-disputed"].editorial_oracle["values"][name]
                ]
            },
        )
        clear = self._make(
            "amount-clear",
            {
                name: {
                    "type": config["type"],
                    "value": (
                        float(value)
                        if config["type"] == "number" and isinstance(value, str)
                        else value
                    ),
                }
                for name, config in oracle["amount-clear"].fields.items()
                for value in [oracle["amount-clear"].editorial_oracle["values"][name]]
            },
        )
        for result, expected in (
            (disputed, ("inspect_dispute", "needs_more_context")),
            (clear, ("suggest_continue", "needs_more_context")),
        ):
            paths = result["evaluation"]["paths"]
            self.assertEqual(paths["direct"]["rule_baseline_action"], expected[0])
            self.assertEqual(
                paths["extracted_only"]["rule_baseline_action"], expected[1]
            )
            self.assertIsNone(paths["direct"]["imported_action"])
            self.assertEqual(
                paths["direct"]["action_source"], "deterministic_path_baseline"
            )
            self.assertEqual(result["evaluation"]["decimal"]["code_total"], "1100.0")
            fields = result["evaluation"]["source_fields"]["fields"]
            for name in ("quantity", "unit_price", "shipping", "computed_total"):
                self.assertTrue(fields[name]["exact_match"], name)
            self.assertTrue(paths["extracted_only"]["honest_under_input"])
            self.assertFalse(paths["extracted_only"]["full_task_completed"])

    def test_span_is_unverified_without_explicit_convention(self):
        case = self.suite.by_id()["source-present"]
        index = case.state.index("林遥")
        answers = self._source_answers(None)
        answers["current_recipient"] = {
            "type": "text",
            "value": "林遥",
            "span": [index, index + 1],
        }
        case = self.suite.by_id()["source-present"]
        result = tv.make_result(
            self.suite,
            case,
            _native_entry(case, answers),
            span_convention=None,
        )
        field = result["evaluation"]["fields"]["current_recipient"]
        self.assertEqual(field["span_status"], "unverified_no_convention")

    def test_span_unicode_units_and_endpoints(self):
        case = self.suite.by_id()["source-unicode-prefix"]
        value = "PO-842"
        char_index = case.state.index(value)
        utf8_start = len(case.state[:char_index].encode("utf-8"))
        utf8_end = utf8_start + len(value.encode("utf-8"))
        utf16_start = len(case.state[:char_index].encode("utf-16-le")) // 2
        utf16_end = utf16_start + len(value.encode("utf-16-le")) // 2
        base = self._source_answers(None)
        for convention, span in (
            (
                {"unit": "utf8", "end": "exclusive"},
                [utf8_start, utf8_end],
            ),
            (
                {"unit": "utf8", "end": "inclusive"},
                [utf8_start, utf8_end - 1],
            ),
            (
                {"unit": "utf16", "end": "exclusive"},
                [utf16_start, utf16_end],
            ),
            (
                {"unit": "codepoint", "end": "exclusive"},
                [char_index, char_index + len(value)],
            ),
        ):
            answers = dict(base)
            answers["current_order_id"] = {
                "type": "text",
                "value": value,
                "span": span,
            }
            result = tv.make_result(
                self.suite,
                self.suite.by_id()["source-unicode-prefix"],
                tv.ResponseEntry(
                    "source-null-identity",
                    "source-unicode-prefix",
                    raw={
                        "model": "clairic",
                        "answers": answers,
                        "truncated": False,
                        "usage": {"input_tokens": 1, "output_tokens": 0},
                        "state_text": self.suite.by_id()["source-unicode-prefix"].state,
                    },
                    http_status=200,
                    value_source="native",
                ),
                span_convention=convention,
            )
            self.assertEqual(
                result["evaluation"]["fields"]["current_order_id"]["span_status"],
                "valid",
                convention,
            )

    def test_native_span_uses_state_text_and_marks_truncated_distinctly(self):
        case = self.suite.by_id()["source-present"]
        answers = self._source_answers("2026-10-20")
        index = case.state.index("林遥")
        answers["current_recipient"] = {
            "type": "text",
            "value": "林遥",
            "span": [index, index + 2],
        }
        result = tv.make_result(
            self.suite,
            case,
            _native_entry(
                case,
                answers,
                state_text=case.state,
                truncated=True,
            ),
            span_convention={"unit": "codepoint", "end": "exclusive"},
        )
        field = result["evaluation"]["fields"]["current_recipient"]
        self.assertEqual(field["span_status"], "valid_in_truncated_state_text")
        self.assertEqual(field["span_text_source"], "response_state_text")

        changed = tv.make_result(
            self.suite,
            case,
            _native_entry(case, answers, state_text="different state text"),
            span_convention={"unit": "codepoint", "end": "exclusive"},
        )
        self.assertEqual(changed["outcome"], tv.OUTCOME_ERROR)
        self.assertIn("outside input bounds", changed["error_detail"])

    def test_bool_and_nonfinite_numbers_rejected_by_typed_field(self):
        case = self.suite.by_id()["amount-disputed"]
        for bad in (True, float("nan"), float("inf")):
            answers = _oracle_entries(self.suite)[3].raw["answers"]
            answers["quantity"] = {"type": "number", "value": bad}
            raw = {
                "model": "clairic",
                "answers": answers,
                "truncated": False,
                "usage": {"input_tokens": 1, "output_tokens": 0},
            }
            if not isinstance(bad, bool):
                raw["answers"] = _oracle_entries(self.suite)[3].raw["answers"]
                raw["answers"]["quantity"] = {"type": "number", "value": bad}
            result = tv.make_result(
                self.suite,
                case,
                tv.ResponseEntry(
                    case.experiment_id,
                    case.case_id,
                    raw=raw,
                    http_status=200,
                    value_source="native",
                ),
                span_convention=None,
            )
            self.assertEqual(result["outcome"], tv.OUTCOME_ERROR, bad)

    def test_native_envelope_is_strict_and_synthetic_is_labeled_separately(self):
        case = self.suite.by_id()["source-missing"]
        answers = self._source_answers(None)
        mutations = (
            lambda raw: raw.pop("model"),
            lambda raw: raw.__setitem__("model", "other"),
            lambda raw: raw.pop("truncated"),
            lambda raw: raw.__setitem__("usage", {}),
            lambda raw: raw.__setitem__("answers", []),
        )
        for mutate in mutations:
            raw = _native_raw(answers)
            mutate(raw)
            result = tv.make_result(
                self.suite,
                case,
                tv.ResponseEntry(
                    case.experiment_id,
                    case.case_id,
                    raw=raw,
                    http_status=200,
                    value_source="native",
                ),
                span_convention=None,
            )
            self.assertEqual(result["outcome"], tv.OUTCOME_ERROR)
        synthetic = tv.make_result(
            self.suite,
            case,
            tv.ResponseEntry(
                case.experiment_id,
                case.case_id,
                raw={"answers": answers},
                value_source="synthetic",
            ),
            span_convention=None,
        )
        self.assertEqual(synthetic["outcome"], tv.OUTCOME_OK)
        self.assertEqual(synthetic["value_source"], "synthetic")

    def test_native_numbers_respect_decimals_and_oversized_int_is_readable(self):
        case = self.suite.by_id()["amount-disputed"]
        answers = _oracle_entries(self.suite)[3].raw["answers"]
        answers["unit_price"] = {"type": "number", "value": 350.001}
        result = tv.make_result(
            self.suite, case, _native_entry(case, answers), span_convention=None
        )
        self.assertEqual(result["outcome"], tv.OUTCOME_ERROR)
        self.assertIn("decimal places", result["error_detail"])
        huge = 10**10000
        huge_answers = _oracle_entries(self.suite)[3].raw["answers"]
        huge_answers["quantity"] = {"type": "number", "value": huge}
        result = tv.make_result(
            self.suite,
            case,
            _native_entry(case, huge_answers),
            span_convention=None,
        )
        self.assertEqual(result["outcome"], tv.OUTCOME_ERROR)
        self.assertIn("finite", result["error_detail"])

    def test_native_estimate_grid_is_enforced(self):
        case = self.suite.by_id()["interval-wide-support"]
        answer = {
            "type": "estimate",
            "value": 5.5,
            "mean": 29.535,
            "median": 5,
            "p10": 2,
            "p90": 8,
        }
        result = tv.make_result(
            self.suite,
            case,
            _native_entry(case, {"completion_days": answer}),
            span_convention=None,
        )
        self.assertEqual(result["outcome"], tv.OUTCOME_ERROR)
        self.assertIn("grid", result["error_detail"])

    def test_interval_quantiles_and_observation_baseline(self):
        answer = {
            "type": "estimate",
            "value": 5,
            "median": 5,
            "p10": 2,
            "p90": 8,
        }
        case = self.suite.by_id()["interval-wide-support"]
        result = tv.make_result(
            self.suite,
            case,
            tv.ResponseEntry(
                case.experiment_id,
                case.case_id,
                raw={
                    "model": "clairic",
                    "answers": {"completion_days": answer},
                    "truncated": False,
                    "usage": {"input_tokens": 1, "output_tokens": 0},
                },
                http_status=200,
                value_source="native",
            ),
            span_convention=None,
        )
        self.assertEqual(result["outcome"], tv.OUTCOME_OK)
        evaluation = result["evaluation"]
        self.assertFalse(evaluation["observation"]["interval_hit"])
        self.assertEqual(evaluation["history_baseline"]["median"], 4.5)
        self.assertEqual(evaluation["history_baseline"]["p10"], 2.0)
        self.assertEqual(evaluation["history_baseline"]["p90"], 8.0)
        self.assertFalse(evaluation["evidence_scope"]["independent_sample_claimed"])

    def test_interval_range_miss_is_a_contract_error(self):
        result = self._make(
            "interval-narrow-support",
            {
                "completion_days": {
                    "type": "estimate",
                    "value": 4.5,
                    "median": 4.5,
                    "p10": 2,
                    "p90": 8,
                }
            },
        )
        self.assertEqual(result["outcome"], tv.OUTCOME_ERROR)
        self.assertIn("min/max", result["error_detail"])

    def test_nonnative_outcomes_stay_distinct(self):
        case = self.suite.by_id()["source-missing"]
        for kind in (tv.OUTCOME_UNKNOWN, tv.OUTCOME_REFUSAL, tv.OUTCOME_ERROR):
            result = tv.make_result(
                self.suite,
                case,
                tv.ResponseEntry(
                    "source-null-identity", "source-missing",
                    outcome_hint=kind, error_detail="explicit imported status",
                ),
                span_convention=None,
            )
            self.assertEqual(result["outcome"], kind)
            self.assertFalse((result["evaluation"] or {}).get("fields"))
            self.assertEqual(result["error_detail"], "explicit imported status")


class TestReplayIntegrity(unittest.TestCase):
    def test_native_contract_error_record_replays_without_changing_input_detail(self):
        suite = tv.load_suite(SUITE)
        case = suite.by_id()["source-missing"]
        entry = _oracle_entries(suite)[0]
        del entry.raw["answers"]["current_delivery_date"]
        record = tv.build_record(suite, [case], [entry], provenance="import")
        with tempfile.TemporaryDirectory() as root:
            path = tv.write_record(Path(root) / "native-error", record)
            replay = tv.replay_record(path, SUITE)
        self.assertEqual(replay["evaluation"]["counts"]["error"], 1)

    def setUp(self):
        self.suite = tv.load_suite(SUITE)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.record = tv.build_record(
            self.suite,
            self.suite.cases,
            _oracle_entries(self.suite),
            provenance=tv.PROVENANCE_IMPORT,
        )
        self.path = self.root / "typed-values-record.json"
        self.path.write_text(
            json.dumps(self.record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp.cleanup()

    def _mutate_and_reject(self, mutate, expected_text: str):
        data = json.loads(self.path.read_text(encoding="utf-8"))
        mutate(data)
        self.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(tv.TypedValuesError) as ctx:
            tv.replay_record(self.path, SUITE)
        self.assertIn(expected_text, str(ctx.exception))

    def test_ok_without_responses_untampered(self):
        report = tv.replay_record(self.path, SUITE)
        self.assertEqual(report["evaluation"]["counts"]["ok"], 7)

    def test_duplicate_case_rejected(self):
        def mutate(data):
            data["results"].append(data["results"][0])
            data["selected_case_ids"].append(data["selected_case_ids"][0])

        self._mutate_and_reject(mutate, "duplicate selected case")

    def test_foreign_case_rejected(self):
        def mutate(data):
            data["selected_case_ids"].append("foreign")

        self._mutate_and_reject(mutate, "foreign")

    def test_tampered_request_rejected(self):
        def mutate(data):
            data["results"][0]["request"]["state"] = "changed"

        self._mutate_and_reject(mutate, "request")

    def test_tampered_response_and_score_rejected(self):
        def mutate(data):
            data["results"][0]["raw"]["answers"]["current_recipient"]["value"] = "周岚"

        self._mutate_and_reject(mutate, "response_digest")

        data = json.loads(self.path.read_text(encoding="utf-8"))
        data["results"][0] = self.record["results"][0]
        data["results"][0]["evaluation"]["fields"]["current_recipient"]["exact_match"] = False
        self.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(tv.TypedValuesError):
            tv.replay_record(self.path, SUITE)

    def test_suite_tamper_rejected(self):
        changed = json.loads(SUITE.read_text(encoding="utf-8"))
        changed["experiments"][0]["cases"][0]["request"]["state"] += " changed"
        bad_suite = self.root / "bad-suite.json"
        bad_suite.write_text(json.dumps(changed, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(tv.TypedValuesError) as ctx:
            tv.replay_record(self.path, bad_suite)
        self.assertIn("suite", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
