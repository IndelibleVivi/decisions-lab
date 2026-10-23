"""Behavioral evidence for native contracts, generated interventions and retained runs."""
import base64
import copy
import io
import json
import socket
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from decision_lab import api_lab as lab
from decision_lab import api_tasks as tasks
from decision_lab.cli import main

ROOT = Path(__file__).resolve().parents[1]


class ApiLabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.suite = lab.load_suite()

    def manifest(self, experiment="probability", route="decisions", ids=None, limit=None,
                 account_id=None):
        rows = lab.select_rows(self.suite, experiment=experiment, case_ids=ids, limit=limit)
        return lab.prepare_payload(self.suite, rows, route=route, account_id=account_id)

    def mixed(self, route="decisions", account_id=None):
        case = {"id": "mixed", "experiment": "custom", "input": "The flag is present; severity is moderate.",
                "questions": [
                    {"id": "category", "type": "choice", "instructions": "Choose category.",
                     "choices": [{"value": "yes", "description": "Present"}, {"value": "unknown", "description": "Unavailable"}]},
                    {"id": "flag", "type": "predicate", "instructions": "Is the flag present?"},
                    {"id": "severity", "type": "score", "instructions": "Rate severity.",
                     "levels": [{"label": "low", "description": "Low severity"}, {"label": "high", "description": "High severity"}]}],
                "rubric": {"questions": {"category": {"kind": "choice", "acceptable": ["yes"]},
                                         "flag": {"kind": "boolean", "expected": True},
                                         "severity": {"kind": "number", "expected": 1.}}}}
        return lab.prepare_payload(lab.Suite({}, [case]), [case], route=route,
                                   account_id=account_id)

    def test_counts_and_complete_rule_space(self):
        result = lab.validate_suite(self.suite)
        self.assertEqual(result["cases"], {"rule-compile": 97, "probability": 27, "visual-criteria": 96})
        self.assertEqual(len({tasks.table(i) for i in range(16)}), 16)
        self.assertEqual(tasks.table(4), "0010")
        self.assertEqual(result["routes"]["decisions"], {"requests": 124, "questions": 208})

    def test_rule_inputs_are_language_and_ids_do_not_reveal_case(self):
        manifest = self.manifest("rule-compile")
        request = next(r for r in manifest["requests"] if r["id"] == "r04-w0-compile-baseline")
        self.assertIn("A成立且B不成立", request["body"]["input"])
        self.assertNotIn("0010", request["body"]["input"])
        self.assertEqual(request["body"]["questions"][0]["name"], "function")
        underspecified = manifest["requests"][-1]["rubric"]
        self.assertEqual(set(underspecified["compatible_tables"]), {"0000", "0010", "0001", "0011"})

    def test_rule_order_id_and_wording_interventions(self):
        manifest = self.manifest("rule-compile")
        variants = {r["rubric"]["condition"]: r for r in manifest["requests"]
                    if r["rubric"].get("group") == "r04-w0" and r["rubric"]["structure"] == "compiled"}
        baseline = variants["baseline"]["body"]["questions"][0]["choices"]
        reverse = variants["reversed"]["body"]["questions"][0]["choices"]
        opaque = variants["opaque"]["body"]["questions"][0]["choices"]
        self.assertEqual(reverse, list(reversed(baseline)))
        self.assertEqual([c["description"] for c in baseline], [c["description"] for c in opaque])
        self.assertNotEqual([c["value"] for c in baseline], [c["value"] for c in opaque])
        self.assertNotEqual(tasks._rule_text(4, 0)[0], tasks._rule_text(4, 1)[0])

    def test_probability_worlds_and_genuine_menus(self):
        manifest = self.manifest()
        groups = {r["rubric"]["group"]: r["rubric"]["world"] for r in manifest["requests"]}
        a, b = tasks.world_truth(groups["correlated"]), tasks.world_truth(groups["anticorrelated"])
        self.assertEqual((a["a"], a["b"]), (.5, .5))
        self.assertEqual((b["a"], b["b"]), (.5, .5))
        self.assertEqual((a["xor"], b["xor"]), (0., 1.))
        coarse = next(r for r in manifest["requests"] if r["id"] == "prob-split-coarse")
        fine = next(r for r in manifest["requests"] if r["id"] == "prob-split-fine")
        self.assertEqual([c["value"] for c in coarse["body"]["questions"][0]["choices"]], ["A", "B"])
        self.assertEqual([c["value"] for c in fine["body"]["questions"][0]["choices"]], ["A1", "A2", "B"])
        self.assertEqual(coarse["body"]["input"], fine["body"]["input"])

    def test_partition_numeric_events_are_self_contained_and_optional(self):
        cases = tasks.partition_event_cases()
        self.assertEqual(len(cases), 3)
        manifest = lab.prepare_payload(lab.Suite({}, cases), cases, route="decisions")
        split = next(request for request in manifest["requests"]
                     if request["id"] == "prob-split-partition")
        instructions = {q["name"]: q["instructions"] for q in split["body"]["questions"]}
        self.assertEqual(set(instructions), {"p_a", "p_a1", "p_a2", "p_region_b"})
        self.assertIn("状态 10 或 11", instructions["p_a"])
        self.assertIn("状态 10", instructions["p_a1"])
        self.assertIn("状态 11", instructions["p_a2"])
        self.assertIn("状态 00 或 01", instructions["p_region_b"])
        report = lab.evaluate(manifest, lab.oracle_entries(manifest))
        self.assertEqual(report["coverage"]["expected_questions"], 12)
        self.assertEqual(report["coverage"]["ok"], 12)
        split_report = next(item for item in report["probability"]
                            if item["unit_id"] == "split")
        self.assertEqual(split_report["numeric_event_mae"], 0.)
        trial = split_report["trials"][0]
        self.assertEqual(trial["numeric_truth"],
                         {"a": .6, "a1": .3, "a2": .3, "region_b": .4})
        self.assertEqual(trial["coherence_errors"], [])

    def test_numeric_partition_violation_uses_explicit_answers(self):
        cases = tasks.partition_event_cases()
        manifest = lab.prepare_payload(lab.Suite({}, cases), cases, route="decisions")
        entries = lab.oracle_entries(manifest)
        answer = next(a for a in entries[-1]["response"]["answers"] if a["name"] == "p_a1")
        answer["choice"] = "0.2"
        answer["probabilities"] = [{"value": f"{i / 10:.1f}", "probability": float(i == 2)} for i in range(11)]
        split = next(r for r in lab.evaluate(manifest, entries)["probability"] if r["unit_id"] == "split")
        self.assertEqual(split["trials"][0]["coherence_errors"], ["partition_additivity"])
        self.assertGreater(split["numeric_event_mae"], 0)

    def test_score_grade_preserves_native_score_separate_from_mean(self):
        normalized = {"outcome": "ok", "value": .25, "distribution_mean": .75}
        self.assertTrue(lab._grade(normalized, {"kind": "number", "expected": .25}))
        self.assertFalse(lab._grade(normalized, {"kind": "number", "expected": .75}))

    def test_joint_choice_mass_is_retained_as_menu_distribution(self):
        manifest = self.manifest(ids=["prob-split-joint"])
        report = lab.evaluate(manifest, lab.oracle_entries(manifest))
        trial = report["probability"][0]["trials"][0]
        self.assertEqual(sum(trial["menu_distribution"].values()), 1)
        self.assertIsNone(trial["numeric_events"])
        self.assertIsNone(trial["coherence_errors"])

    def test_unmatched_nullable_seeds_are_not_paired_or_crashed(self):
        rows = copy.deepcopy(lab.select_rows(self.suite, experiment="probability",
                             case_ids=["prob-correlated-single-a", "prob-correlated-bundled"]))
        rows[1]["trial"] = {"seed": 7}
        manifest = lab.prepare_payload(self.suite, rows, route="decisions")
        report = lab.evaluate(manifest, lab.oracle_entries(manifest))
        self.assertIsNone(report["probability"][0]["single_bundled_delta"])

    def test_order_consistency_checks_every_variant_and_replicate(self):
        rows = [r for r in self.suite.rows if r["id"].startswith("r00-w0-compile")]
        manifest = lab.prepare_payload(self.suite, rows, route="decisions", replicates=2)
        entries = lab.oracle_entries(manifest)
        entry = next(e for e in entries if "reversed-r1" in e["request_id"])
        request = next(r for r in manifest["requests"] if r["id"] == entry["request_id"])
        answer = entry["response"]["answers"][0]
        choice = next(c["value"] for c in request["body"]["questions"][0]["choices"]
                      if c["value"] != answer["choice"] and c["value"] in request["rubric"]["choice_tables"])
        answer["choice"] = choice
        answer["probabilities"] = [{"value": c["value"], "probability": float(c["value"] == choice)} for c in request["body"]["questions"][0]["choices"]]
        summary = lab.evaluate(manifest, entries)["rule_compile"]["order_id_consistency"][0]
        self.assertTrue(summary["complete"])
        self.assertFalse(summary["same_prediction"])
        self.assertEqual([r["same_prediction"] for r in summary["replicates"]], [True, False])

    def test_visual_repeat_compatibility_keeps_all_values_and_truth(self):
        rows = [r for r in self.suite.rows if r["experiment"] == "visual-criteria"][:1]
        manifest = lab.prepare_payload(self.suite, rows, route="jev", replicates=2)
        report = lab.evaluate(manifest, lab.oracle_entries(manifest))
        cases = report["visual_criteria"]["cases"][rows[0]["rubric"]["group"]]["text"]
        self.assertEqual(cases["count"], 2)
        self.assertEqual({r["trial"]["replicate"] for r in cases["trials"]}, {0, 1})
        self.assertTrue(all(r["defined_relation"] == r["truth"] for r in cases["trials"]))

    def test_single_and_bundled_questions_are_identical(self):
        manifest = self.manifest()
        for group in ("correlated", "anticorrelated", "split"):
            bundled = next(r for r in manifest["requests"] if r["id"] == f"prob-{group}-bundled")
            singles = [r for r in manifest["requests"] if r["id"].startswith(f"prob-{group}-single-")]
            self.assertEqual([r["body"]["questions"][0] for r in singles], bundled["body"]["questions"])
            self.assertTrue(all(r["body"]["input"] == bundled["body"]["input"] for r in singles))

    def test_labels_are_structurally_excluded_from_native_request(self):
        case = copy.deepcopy(self.suite.rows[0])
        other = copy.deepcopy(case)
        other["rubric"]["questions"]["function"]["acceptable"] = ["f01"]
        old = lab.prepare_payload(self.suite, [case], route="decisions")
        new = lab.prepare_payload(self.suite, [other], route="decisions")
        self.assertEqual(old["requests"][0]["body"], new["requests"][0]["body"])
        self.assertEqual(old["requests"][0]["request_digest"], new["requests"][0]["request_digest"])
        self.assertNotEqual(old["requests"][0]["rubric_digest"], new["requests"][0]["rubric_digest"])

    def test_visual_conditions_keep_target_and_swap_only_reference_definitions(self):
        manifest = self.manifest("visual-criteria", "jev")
        self.assertEqual(len(manifest["requests"]), 96)
        cases = {}
        for request in manifest["requests"]:
            rubric, body = request["rubric"], request["body"]
            cases.setdefault(rubric["group"], {})[rubric["condition"]] = request
            target = body["state"]["target"]
            self.assertIn(target, body["assets"])  # Especially the text-criteria condition.
            for asset in body["assets"].values():
                data = base64.b64decode(asset["data_base64"])
                self.assertEqual(struct.unpack(">II", data[16:24]), (320, 320))
            self.assertEqual(tasks.relation(*rubric["geometry"]), rubric["family"])
        self.assertEqual(len(cases), 24)
        for variants in cases.values():
            targets = [v["body"]["assets"][v["body"]["state"]["target"]] for v in variants.values()]
            self.assertTrue(all(target == targets[0] for target in targets))
            before, after = variants["image"], variants["swapped-image"]
            self.assertEqual(before["body"]["state"], after["body"]["state"])
            self.assertEqual(before["body"]["questions"], after["body"]["questions"])
            self.assertNotEqual(before["body"]["assets"]["r01"], after["body"]["assets"]["r01"])
            self.assertNotEqual(before["rubric"]["questions"]["relation"], after["rubric"]["questions"]["relation"])
            self.assertTrue(all("包含" not in text and "接触" not in text
                                for text in after["body"]["questions"]["relation"]["criteria"].values()))

    def test_png_pixels_follow_retained_geometry(self):
        manifest = self.manifest("visual-criteria", "jev")
        for request in manifest["requests"][::4]:
            body, geometry = request["body"], request["rubric"]["geometry"]
            data = base64.b64decode(body["assets"][body["state"]["target"]]["data_base64"])
            offset, compressed = 8, b""
            while offset < len(data):
                size = struct.unpack(">I", data[offset:offset + 4])[0]
                kind = data[offset + 4:offset + 8]
                if kind == b"IDAT":
                    compressed += data[offset + 8:offset + 8 + size]
                offset += 12 + size
            raw = zlib.decompress(compressed)
            def pixel(x, y):
                position = y * (320 * 3 + 1) + 1 + x * 3
                return raw[position:position + 3]
            x, y, w, h = geometry[0]
            a, b, u, v = geometry[1]
            self.assertNotEqual(pixel(x, y), pixel(0, 0))
            self.assertEqual(pixel(x + 10, y + 10), pixel(0, 0))
            self.assertNotEqual(pixel(a + u // 2, b + v // 2), pixel(0, 0))

    def test_visual_native_route_and_size_guard(self):
        with self.assertRaises(lab.ApiLabError):
            self.manifest("visual-criteria", "decisions")
        manifest = self.manifest("visual-criteria", "jev", limit=1)
        body = manifest["requests"][0]["body"]
        asset = next(iter(body["assets"].values()))
        blob = bytearray(base64.b64decode(asset["data_base64"]))
        blob[16:20] = struct.pack(">I", 64)
        asset["data_base64"] = base64.b64encode(blob).decode()
        with self.assertRaises(lab.ApiLabError):
            lab._check_native(body, manifest["requests"][0]["required_headers"], "jev")

    def test_mixed_primitives_both_routes(self):
        for route in lab.ROUTES:
            manifest = self.mixed(route, account_id="a" * 32 if route in lab.CLOUDFLARE_ROUTES else None)
            results = lab.evaluate(manifest, lab.synthetic_entries(manifest))
            self.assertEqual(results["coverage"]["ok"], 3)
            self.assertEqual(results["accuracy_on_valid_answers"], 1.)
            if route == "jev":
                self.assertEqual(manifest["requests"][0]["body"]["questions"]["severity"]["criteria"],
                                 ["Low severity", "High severity"])

    def test_native_clef_and_openrouter_route_contracts(self):
        account = "a" * 32
        for route, model, path_model in (
            ("clef-flash", "clef-flash", "@cf/cloudflare/clef-flash"),
            ("clef", "clef", "@cf/cloudflare/clef"),
        ):
            with self.subTest(route=route):
                manifest = self.mixed(route, account_id=account)
                body = manifest["requests"][0]["body"]
                self.assertEqual(manifest["model"], model)
                self.assertEqual(body["model"], model)
                self.assertEqual(manifest["endpoint"],
                                 f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{path_model}")
                self.assertNotIn("name", body["questions"]["category"])
                self.assertNotIn("choices", body["questions"]["category"])
                self.assertEqual(body["questions"]["flag"]["type"], "noul")
                with self.assertRaises(lab.ApiLabError):
                    self.mixed(route)
                with self.assertRaises(lab.ApiLabError):
                    lab.prepare_payload(lab.Suite({}, [self.suite.rows[0]]),
                                        [self.suite.rows[0]], route=route,
                                        model=path_model, account_id=account)

        manifest = self.mixed("openrouter-decisions")
        self.assertEqual(manifest["model"], "baseten/mammoth-1:free")
        self.assertEqual(manifest["endpoint"], "https://openrouter.ai/api/alpha/decisions")
        for model in ("baseten/mammoth-1:free", "inception/mercury-decide:free",
                      "typesafe/jev-1.14", "openai/gpt-6-luna-decisions"):
            candidate = lab.prepare_payload(lab.Suite({}, [self.suite.rows[0]]),
                                            [self.suite.rows[0]], route="openrouter-decisions",
                                            model=model)
            self.assertEqual(candidate["model"], model)
            self.assertNotIn("cost_policy", candidate)
        self.assertIn("state", manifest["requests"][0]["body"])
        self.assertNotIn("input", manifest["requests"][0]["body"])
        with self.assertRaises(lab.ApiLabError):
            lab.prepare_payload(lab.Suite({}, [self.suite.rows[0]]),
                                [self.suite.rows[0]], route="openrouter-decisions",
                                model="unknown/route:free")
        with self.assertRaises(lab.ApiLabError):
            self.manifest("visual-criteria", "clef", account_id=account)
        with self.assertRaises(lab.ApiLabError):
            self.manifest("visual-criteria", "openrouter-decisions")

    def test_cloudflare_wrapper_and_openrouter_identity_are_checked(self):
        manifest = self.mixed("clef-flash", account_id="a" * 32)
        entries = lab.synthetic_entries(manifest)
        result = lab.evaluate(manifest, entries)
        self.assertEqual(result["coverage"]["ok"], 3)
        self.assertEqual(result["requests"][0]["returned_model"], "clef-flash")
        answer = entries[0]["response"]["result"]
        for broken in (
            answer,
            {"success": True, "result": {**answer, "answers": []}},
            {"success": True, "result": {**answer, "model": "@cf/cloudflare/clef"}},
            {"success": True, "errors": ["failed"], "result": answer},
        ):
            changed = copy.deepcopy(entries)
            changed[0]["response"] = broken
            self.assertEqual(lab.evaluate(manifest, changed)["coverage"]["ok"], 0)
        for broken in (
            {"success": True},
            {"success": False, "result": answer},
            {"success": True, "result": {"answers": answer["answers"]}},
        ):
            changed = copy.deepcopy(entries)
            changed[0]["response"] = broken
            self.assertEqual(lab.evaluate(manifest, changed)["coverage"]["ok"], 0)
        metadata = copy.deepcopy(entries)
        metadata[0]["response"]["request_id"] = "provider-metadata"
        metadata[0]["response"]["result"]["model"] = "@cf/cloudflare/clef-flash"
        self.assertEqual(lab.evaluate(manifest, metadata)["coverage"]["ok"], 3)
        changed = copy.deepcopy(entries)
        changed[0]["response"]["result"]["answers"]["category"]["type"] = "noul"
        evaluated = lab.evaluate(manifest, changed)
        self.assertEqual(evaluated["coverage"]["ok"], 2)
        self.assertEqual(evaluated["coverage"]["error"], 1)

        manifest = self.mixed("openrouter-decisions")
        entries = lab.synthetic_entries(manifest)
        entries[0]["provider"] = "Prime Intellect"
        result = lab.evaluate(manifest, entries)
        self.assertEqual(result["requests"][0]["returned_provider"], "Prime Intellect")
        lists = copy.deepcopy(entries)
        lists[0]["response"]["answers"] = list(lists[0]["response"]["answers"].values())
        self.assertEqual(lab.evaluate(manifest, lists)["coverage"]["error"], 3)
        error = copy.deepcopy(entries)
        error[0]["response"] = {"error": {"message": "upstream failed"}}
        self.assertEqual(lab.evaluate(manifest, error)["coverage"]["error"], 3)

    def test_native_score_scalar_and_distribution_mean_remain_separate(self):
        manifest = self.mixed("openrouter-decisions")
        entries = lab.synthetic_entries(manifest)
        score = entries[0]["response"]["answers"]["severity"]
        self.assertEqual(lab.evaluate(manifest, entries)["coverage"]["ok"], 3)
        score["score"] = .25
        evaluated = lab.evaluate(manifest, entries)
        severity = next(q for q in evaluated["requests"][0]["questions"]
                        if q["question_id"] == "severity")
        self.assertEqual(severity["outcome"], "ok")
        self.assertEqual(severity["value"], .25)
        self.assertEqual(severity["distribution_mean"], 1.)
        self.assertFalse(severity["correct"])

    def test_retained_manifest_does_not_require_new_billing_metadata(self):
        manifest = self.manifest(limit=1)
        self.assertNotIn("cost_policy", manifest)
        self.assertEqual(lab.evaluate(manifest, lab.oracle_entries(manifest))["accuracy_on_valid_answers"], 1.)

    def test_openrouter_rounding_preserves_raw_mass_and_other_routes_remain_strict(self):
        criteria = {f"f{i:02d}": f"function {i}" for i in range(17)}
        question = {"type": "choice", "criteria": criteria}
        probabilities = dict.fromkeys(criteria, 0.)
        probabilities.update(f01=.01, f02=.01, f04=.9400000000000001, f12=.02, f16=.01)
        answer = {"type": "choice", "choice": "f04", "confidence": .94,
                  "probabilities": probabilities}
        normalized = lab.normalize_answer(question, answer, "openrouter-decisions")
        self.assertEqual([p["probability"] for p in normalized["probabilities"]], list(probabilities.values()))
        self.assertAlmostEqual(normalized["probability_precision"]["returned_sum"], .99)
        self.assertFalse(normalized["probability_precision"]["renormalized"])
        for route in ("jev", "clef", "clef-flash"):
            with self.subTest(route=route), self.assertRaises(lab.ApiLabError):
                lab.normalize_answer(question, answer, route)
        for bad in (dict.fromkeys(criteria, 0.), {**probabilities, "f04": .7},
                    {**probabilities, "f04": .941}, {**probabilities, "f04": float("nan")}):
            with self.assertRaises(lab.ApiLabError):
                lab.normalize_answer(question, {**answer, "probabilities": bad}, "openrouter-decisions")

    def test_openrouter_rounded_score_keeps_native_scalar(self):
        question = {"type": "score", "criteria": ["low", "medium", "high"]}
        answer = {"type": "score", "score": .98, "confidence": .33,
                  "probabilities": {"0": .33, "1": .33, "2": .33}}
        result = lab.normalize_answer(question, answer, "openrouter-decisions")
        self.assertEqual(result["value"], .98)
        self.assertEqual(result["distribution_mean"], .99)
        self.assertAlmostEqual(result["probability_precision"]["returned_sum"], .99)

    def test_refusal_and_malformed_question_preserve_siblings(self):
        manifest = self.mixed()
        entries = lab.synthetic_entries(manifest)
        entries[0]["response"]["answers"][0] = {"type": "refusal", "name": "category"}
        result = lab.evaluate(manifest, entries)
        self.assertEqual(result["coverage"]["refusal"], 1)
        self.assertEqual(result["coverage"]["ok"], 2)
        entries[0]["response"]["answers"][1]["probability"] = -1.
        result = lab.evaluate(manifest, entries)
        self.assertEqual((result["coverage"]["refusal"], result["coverage"]["error"], result["coverage"]["ok"]), (1, 1, 1))

    def test_missing_duplicate_foreign_and_malformed_names(self):
        manifest = self.mixed()
        for mutation in ("missing", "duplicate", "foreign", "invalid_name"):
            entries = lab.synthetic_entries(manifest)
            answers = entries[0]["response"]["answers"]
            if mutation == "missing":
                del answers[0]
            elif mutation == "duplicate":
                answers.append(copy.deepcopy(answers[0]))
            elif mutation == "foreign":
                answers.append({"type": "predicate", "name": "other", "probability": .5})
            else:
                answers[0]["name"] = []
            result = lab.evaluate(manifest, entries)
            self.assertGreaterEqual(result["coverage"]["ok"], 2)
            if mutation != "foreign":
                self.assertEqual(result["coverage"]["error"], 1)
            else:
                self.assertTrue(result["requests"][0]["contract_issues"])

    def test_answer_order_is_a_contract_when_the_list_is_complete(self):
        manifest = self.mixed()
        entries = lab.synthetic_entries(manifest)
        entries[0]["response"]["answers"][:2] = reversed(entries[0]["response"]["answers"][:2])
        result = lab.evaluate(manifest, entries)
        self.assertEqual(result["coverage"]["error"], 2)
        self.assertEqual(result["coverage"]["ok"], 1)

    def test_choice_distribution_contract_and_typed_values(self):
        q = {"type": "choice", "choices": [{"value": True}, {"value": "true"}]}
        answer = {"type": "choice", "choice": True, "confidence": .8,
                  "probabilities": [{"value": True, "probability": .7}, {"value": "true", "probability": .3}]}
        self.assertIs(lab.normalize_answer(q, answer, "decisions")["value"], True)
        mutations = [
            {"choice": "foreign"}, {"choice": "true"},
            {"probabilities": [{"value": True, "probability": 1.}]},
            {"probabilities": [{"value": True, "probability": .5}, {"value": True, "probability": .5}]},
            {"probabilities": [{"value": True, "probability": .7}, {"value": "true", "probability": .7}]},
            {"confidence": float("nan")}, {"confidence": True},
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation), self.assertRaises(lab.ApiLabError):
                lab.normalize_answer(q, {**answer, **mutation}, "decisions")

    def test_score_native_index_map_and_openai_labels(self):
        q = {"type": "score", "criteria": ["Low", "High"]}
        good = {"type": "score", "score": .75, "confidence": .8,
                "legend": {"0": "Low", "1": "High"}, "probabilities": {"0": .25, "1": .75}}
        normalized = lab.normalize_answer(q, good, "jev")
        self.assertEqual(normalized["distribution_mean"], .75)
        for mutation in ({"probabilities": [.25, .75]}, {"score": 2}, {"legend": {"0": "High", "1": "Low"}}):
            with self.assertRaises(lab.ApiLabError):
                lab.normalize_answer(q, {**good, **mutation}, "jev")
        q = {"type": "score", "levels": [{"label": "Low"}, {"label": "High"}]}
        answer = {"type": "score", "score": .75, "confidence": .8,
                  "probabilities": [{"label": "Low", "value": 0, "probability": .25},
                                    {"label": "High", "value": 1, "probability": .75}]}
        self.assertEqual(lab.normalize_answer(q, answer, "decisions")["value"], .75)

    def test_oracle_score_supports_fractional_rubric_and_uniform_expectation(self):
        case = {
            "id": "fractional-score",
            "experiment": "custom",
            "input": "Score the fixture.",
            "questions": [{
                "id": "quality",
                "type": "score",
                "instructions": "Rate quality.",
                "levels": [{"label": label, "description": label}
                           for label in ("low", "medium", "high")],
            }],
            "rubric": {"questions": {
                "quality": {"kind": "number", "expected": 1.5, "tolerance": 1e-6}}},
        }
        manifest = lab.prepare_payload(lab.Suite({}, [case]), [case], route="decisions")
        perfect = lab.oracle_entries(manifest, mode="perfect")
        self.assertEqual(lab.evaluate(manifest, perfect)["accuracy_on_valid_answers"], 1.)
        score = perfect[0]["response"]["answers"][0]
        self.assertEqual(score["probabilities"],
                         [{"label": "low", "value": 0, "probability": 0.},
                          {"label": "medium", "value": 1, "probability": .5},
                          {"label": "high", "value": 2, "probability": .5}])
        self.assertEqual(score["score"], 1.5)
        uniform = lab.oracle_entries(manifest, mode="uniform")[0]["response"]["answers"][0]
        self.assertEqual(uniform["score"], 1.)
        normalized = lab.normalize_answer(
            manifest["requests"][0]["body"]["questions"][0], uniform, "decisions")
        self.assertEqual(normalized["score"] if "score" in normalized else uniform["score"], 1.)
        self.assertEqual(normalized["distribution_mean"], 1.)

    def test_trial_family_and_split_consistency_are_validated(self):
        rows = lab.select_rows(self.suite, experiment="probability",
                               case_ids=["prob-split-bundled"])
        manifest = lab.prepare_payload(self.suite, rows, route="decisions", replicates=2)
        changed = copy.deepcopy(manifest)
        changed["requests"][1]["trial"]["source_family"] = "other-family"
        changed.pop("manifest_digest")
        changed["manifest_digest"] = lab.digest(changed)
        with self.assertRaises(lab.ApiLabError) as raised:
            lab.validate_manifest(changed)
        self.assertIn("multiple source families", str(raised.exception))
        changed = copy.deepcopy(manifest)
        changed["requests"][1]["trial"]["split"] = "test"
        changed.pop("manifest_digest")
        changed["manifest_digest"] = lab.digest(changed)
        with self.assertRaises(lab.ApiLabError) as raised:
            lab.validate_manifest(changed)
        self.assertIn("spans multiple splits", str(raised.exception))

    def test_jev_refusal_is_not_invented(self):
        manifest = self.mixed("jev")
        entries = lab.synthetic_entries(manifest)
        entries[0]["response"]["answers"]["category"] = {"type": "refusal"}
        report = lab.evaluate(manifest, entries)
        self.assertEqual(report["coverage"]["error"], 1)
        self.assertEqual(report["coverage"]["refusal"], 0)
        self.assertEqual(report["coverage"]["ok"], 2)

    def test_http_and_transport_errors_are_not_unknown(self):
        manifest = self.mixed()
        for entry in ({"request_id": "mixed", "http_status": 503, "response": {"message": "busy"}},
                      {"request_id": "mixed", "error": "timeout"}):
            result = lab.evaluate(manifest, [entry])
            self.assertEqual(result["coverage"]["error"], 3)
            self.assertEqual(result["coverage"]["unknown"], 0)

    def test_insufficient_is_a_correct_ordinary_answer(self):
        manifest = self.manifest("rule-compile", ids=["rule-necessary-only"])
        result = lab.evaluate(manifest, lab.synthetic_entries(manifest))
        self.assertEqual(result["coverage"]["ok"], 1)
        self.assertEqual(result["accuracy_on_valid_answers"], 1.)

    def test_unknown_requires_explicit_task_semantics(self):
        manifest = self.mixed()
        manifest["requests"][0]["rubric"]["questions"]["category"]["unknown_values"] = ["unknown"]
        r = manifest["requests"][0]; r["rubric_digest"] = lab.digest(r["rubric"])
        manifest.pop("manifest_digest"); manifest["manifest_digest"] = lab.digest(manifest)
        entries = lab.synthetic_entries(manifest)
        answer = entries[0]["response"]["answers"][0]
        answer["choice"] = "unknown"
        answer["probabilities"] = [{"value": "yes", "probability": 0.}, {"value": "unknown", "probability": 1.}]
        result = lab.evaluate(manifest, entries)
        self.assertEqual(result["coverage"]["unknown"], 1)
        self.assertEqual(result["coverage"]["ok"], 2)

    def test_compiled_counterexamples_and_consistency_are_not_accuracy(self):
        manifest = self.manifest("rule-compile", ids=["r04-w0-compile-baseline"])
        entries = lab.synthetic_entries(manifest)
        answer = entries[0]["response"]["answers"][0]
        answer["choice"] = "f00"
        answer["probabilities"] = [{"value": value["value"], "probability": float(value["value"] == "f00")}
                                   for value in manifest["requests"][0]["body"]["questions"][0]["choices"]]
        result = lab.evaluate(manifest, entries)
        counter = result["rule_compile"]["cases"][0]
        self.assertEqual(counter["hamming_error"], 1)
        self.assertEqual(counter["counterexample_states"], [{"state": "10", "expected": "1", "actual": "0"}])
        self.assertIsNone(result["rule_compile"]["order_id_consistency"][0]["same_prediction"])

    def test_probability_report_calculates_mass_and_numeric_coherence(self):
        manifest = self.manifest()
        report = lab.evaluate(manifest, lab.synthetic_entries(manifest))
        split = next(item for item in report["probability"] if item["group"] == "split")
        self.assertAlmostEqual(split["coarse_fine_mass_delta"], -.15)
        self.assertTrue(all(value == 0 for value in split["numeric_truth_error"]["single"].values()))
        self.assertEqual(split["coherence"]["single"]["violations"], [])
        self.assertEqual(split["single_bundled_delta"]["a"], 0.)

    def test_coherence_and_accuracy_discriminate_different_failures(self):
        manifest = self.manifest(ids=["prob-correlated-bundled"])
        entries = lab.synthetic_entries(manifest)
        def select(answer, value):
            answer["type"] = "choice"
            answer["confidence"] = .9
            answer["choice"] = value
            answer["probabilities"] = [{"value": f"{i / 10:.1f}",
                                        "probability": float(f"{i / 10:.1f}" == value)} for i in range(11)]
        for answer in entries[0]["response"]["answers"]:
            select(answer, "0.0")
        report = lab.evaluate(manifest, entries)["probability"][0]
        self.assertEqual(report["coherence"]["bundled"]["violations"], [])
        self.assertEqual(report["numeric_truth_error"]["bundled"]["a"], .5)
        by_id = {answer["name"]: answer for answer in entries[0]["response"]["answers"]}
        select(by_id["p_a"], "0.5"); select(by_id["p_b"], "0.5"); select(by_id["p_and"], "1.0")
        report = lab.evaluate(manifest, entries)["probability"][0]
        self.assertIn("intersection_bounds", report["coherence"]["bundled"]["violations"])

    def test_two_replicates_get_two_independent_coherence_checks(self):
        rows = lab.select_rows(self.suite, experiment="probability",
                               case_ids=["prob-correlated-bundled"])
        manifest = lab.prepare_payload(self.suite, rows, route="decisions", replicates=2)
        entries = lab.oracle_entries(manifest)
        by_name = {answer["name"]: answer for answer in entries[1]["response"]["answers"]}
        for name, value in (("p_a", "0.5"), ("p_b", "0.5"), ("p_and", "1.0")):
            by_name[name]["choice"] = value
            by_name[name]["probabilities"] = [
                {"value": f"{index / 10:.1f}",
                 "probability": float(f"{index / 10:.1f}" == value)}
                for index in range(11)]
        report = lab.evaluate(manifest, entries)["probability"][0]
        self.assertEqual(report["bundled"]["replicates"], 2)
        self.assertEqual(report["coherence"]["checkable_replicates"], 2)
        self.assertEqual(report["coherence"]["violation_replicates"], 1)
        per_trial = sorted((row["trial"]["replicate"], bool(row["coherence_errors"]))
                           for row in report["trials"] if row["condition"] == "bundled")
        self.assertEqual(per_trial, [(0, False), (1, True)])

    def test_rule_and_visual_pairs_remain_complete_with_repeats(self):
        rows = lab.select_rows(self.suite, experiment="rule-compile", case_ids=[
            "r04-w0-compile-baseline", "r04-w0-compile-reversed",
            "r04-w0-compile-opaque"])
        rule = lab.prepare_payload(self.suite, rows, route="decisions", replicates=2)
        consistency = lab.evaluate(rule, lab.oracle_entries(rule))[
            "rule_compile"]["order_id_consistency"][0]
        self.assertTrue(consistency["complete"])
        self.assertTrue(consistency["same_prediction"])
        rows = lab.select_rows(self.suite, experiment="visual-criteria", case_ids=[
            "visual-001-image", "visual-001-swapped-image"])
        visual = lab.prepare_payload(self.suite, rows, route="jev", replicates=2)
        entries = lab.oracle_entries(visual)
        first = lab.evaluate(visual, entries)["visual_criteria"]
        second = lab.evaluate(visual, list(reversed(entries)))["visual_criteria"]
        self.assertEqual(len(first["definition_swap"]), 2)
        self.assertEqual(first["counts"], {"image": 2, "swapped-image": 2})
        self.assertEqual(first["definition_swap"], second["definition_swap"])

    def test_visual_label_flip_alone_is_not_success(self):
        manifest = self.manifest("visual-criteria", "jev",
                                 ids=["visual-001-image", "visual-001-swapped-image"])
        entries = lab.synthetic_entries(manifest)
        for entry, choice in zip(entries, ["K2", "K1"]):
            answer = entry["response"]["answers"]["relation"]
            answer["choice"] = choice
            answer["probabilities"] = {key: float(key == choice) for key in ("K1", "K2", "K3")}
        result = lab.evaluate(manifest, entries)["visual_criteria"]["definition_swap"][0]
        self.assertTrue(result["changed_label"])
        self.assertFalse(result["followed_definitions"])

    def test_partial_import_uses_manifest_denominators(self):
        manifest = self.manifest()
        entries = lab.synthetic_entries(manifest)[:1]
        with self.assertRaises(lab.ApiLabError):
            lab.build_record(manifest, entries, provenance="imported")
        record = lab.build_record(manifest, entries, provenance="imported", allow_partial=True)
        self.assertIsNone(record["synthetic"])
        report = lab.evaluate(record["manifest"], record["responses"])
        self.assertEqual(report["coverage"]["expected_requests"], 27)
        self.assertEqual(report["coverage"]["received_requests"], 1)
        self.assertEqual(report["coverage"]["expected_questions"], 39)
        self.assertEqual(report["coverage"]["missing_question_slots"], 38)
        for malformed in (entries + entries, [{**entries[0], "request_id": "foreign"}]):
            with self.assertRaises(lab.ApiLabError):
                lab.build_record(manifest, malformed, provenance="imported", allow_partial=True)

    def test_perfect_oracle_is_offline_fixture_semantics(self):
        rows = lab.select_rows(self.suite, experiment="probability")
        manifest = lab.prepare_payload(self.suite, rows, route="decisions")
        entries = lab.oracle_entries(manifest, mode="perfect")
        self.assertEqual(len(entries), 27)
        self.assertEqual(len(manifest["requests"]), 27)
        report = lab.evaluate(manifest, entries)
        self.assertEqual(report["coverage"]["expected_questions"], 39)
        self.assertEqual(report["coverage"]["ok"], 39)
        self.assertEqual(report["accuracy_on_valid_answers"], 1.)
        self.assertEqual(lab.oracle_entries(manifest, mode="uniform")[0]["request_id"],
                         entries[0]["request_id"])
        wrong = lab.evaluate(manifest, lab.oracle_entries(manifest, mode="wrong"))
        self.assertLess(wrong["accuracy_on_valid_answers"], 1.)

    def test_replicates_keep_unique_ids_identical_bodies_and_trial_identity(self):
        rows = lab.select_rows(self.suite, experiment="probability",
                               case_ids=["prob-split-bundled"])
        manifest = lab.prepare_payload(self.suite, rows, route="decisions", replicates=3)
        self.assertEqual([r["id"] for r in manifest["requests"]],
                         ["prob-split-bundled", "prob-split-bundled-r1",
                          "prob-split-bundled-r2"])
        self.assertEqual([r["trial"]["replicate"] for r in manifest["requests"]], [0, 1, 2])
        self.assertEqual({r["trial"]["unit_id"] for r in manifest["requests"]}, {"split"})
        self.assertTrue(all(r["body"] == manifest["requests"][0]["body"]
                            for r in manifest["requests"]))
        report = lab.evaluate(manifest, lab.oracle_entries(manifest))
        self.assertEqual(report["coverage"]["ok"], 15)
        split = report["probability"][0]
        self.assertEqual(split["counts"], {"bundled": 3})
        self.assertEqual(split["bundled"]["replicates"], 3)
        self.assertEqual(split["bundled"]["mean_absolute_error"], 0.)

    def test_custom_case_trial_identity_is_preserved_across_replicates(self):
        case = {
            "id": "custom-trial",
            "experiment": "custom",
            "input": "A fixture.",
            "questions": [{
                "id": "flag",
                "type": "predicate",
                "instructions": "Is the fixture present?",
            }],
            "rubric": {
                "questions": {"flag": {"kind": "boolean", "expected": True}},
            },
            "trial": {
                "unit_id": "fixture-unit",
                "source_family": "fixture-family",
                "condition": "with-context",
                "replicate": 4,
                "split": "held-out",
                "seed": 17,
            },
        }
        manifest = lab.prepare_payload(
            lab.Suite({}, [case]), [case], route="decisions", replicates=2)
        self.assertEqual([request["trial"] for request in manifest["requests"]], [
            case["trial"],
            {**case["trial"], "replicate": 5},
        ])
        self.assertEqual([request["id"] for request in manifest["requests"]],
                         ["custom-trial-r4", "custom-trial-r5"])

    def test_repeat_order_invariance_and_explicit_missing_repeat(self):
        rows = lab.select_rows(self.suite, experiment="probability",
                               case_ids=["prob-correlated-bundled"])
        manifest = lab.prepare_payload(self.suite, rows, route="decisions", replicates=2)
        entries = lab.oracle_entries(manifest)
        entries[1]["response"]["answers"] = [
            {**answer, "choice": "0.0", "probabilities": [
                {"value": f"{index / 10:.1f}", "probability": float(index == 0)}
                for index in range(11)]}
            for answer in entries[1]["response"]["answers"]
        ]
        first = lab.evaluate(manifest, entries)["probability"][0]
        second = lab.evaluate(manifest, list(reversed(entries)))["probability"][0]
        self.assertEqual(first["bundled"]["replicates"], 2)
        self.assertAlmostEqual(first["bundled"]["mean_absolute_error"], .2)
        self.assertEqual(first["bundled"]["mean_absolute_error"],
                         second["bundled"]["mean_absolute_error"])
        self.assertEqual({row["trial"]["replicate"] for row in first["trials"]}, {0, 1})
        partial = lab.evaluate(manifest, entries[:1])["probability"][0]
        self.assertEqual(partial["bundled"]["replicates"], 1)
        self.assertEqual(partial["counts"], {"bundled": 1})

    def test_duplicate_logical_slots_and_malformed_trial_are_rejected(self):
        rows = lab.select_rows(self.suite, experiment="probability",
                               case_ids=["prob-correlated-bundled"])
        manifest = lab.prepare_payload(self.suite, rows, route="decisions", replicates=2)
        duplicate = copy.deepcopy(manifest)
        duplicate["requests"][1]["trial"]["replicate"] = 0
        duplicate.pop("manifest_digest")
        duplicate["manifest_digest"] = lab.digest(duplicate)
        with self.assertRaises(lab.ApiLabError) as raised:
            lab.validate_manifest(duplicate)
        self.assertIn("duplicate logical trial slot", str(raised.exception))
        for mutate in (
            lambda trial: trial.update({"replicate": True}),
            lambda trial: trial.update({"seed": -1}),
            lambda trial: trial.update({"condition": ""}),
            lambda trial: trial.update({"unknown": 1}),
        ):
            malformed = copy.deepcopy(manifest)
            mutate(malformed["requests"][0]["trial"])
            malformed.pop("manifest_digest")
            malformed["manifest_digest"] = lab.digest(malformed)
            with self.subTest(trial=malformed["requests"][0]["trial"]), \
                    self.assertRaises(lab.ApiLabError):
                lab.validate_manifest(malformed)

    def test_old_manifest_replays_with_default_trial_without_mutation(self):
        manifest = self.manifest(ids=["prob-correlated-bundled"])
        for request in manifest["requests"]:
            request.pop("trial")
        manifest.pop("manifest_digest")
        manifest["manifest_digest"] = lab.digest(manifest)
        before = copy.deepcopy(manifest)
        report = lab.evaluate(manifest, lab.oracle_entries(manifest))
        self.assertEqual(manifest, before)
        trial = report["requests"][0]["trial"]
        self.assertEqual(trial["replicate"], 0)
        self.assertEqual(trial["split"], "unspecified")
        self.assertIsNone(trial["seed"])

    def test_snapshot_replay_and_two_rubrics(self):
        manifest = self.mixed()
        record = lab.build_record(manifest, lab.synthetic_entries(manifest), provenance="synthetic")
        with tempfile.TemporaryDirectory() as parent:
            directory = Path(parent) / "run"
            path = lab.write_record(directory, record)
            original_bytes = path.read_bytes()
            # A changed builder/default model cannot invalidate old evidence.
            with patch.object(tasks, "all_cases", side_effect=AssertionError("must not regenerate")), \
                 patch.dict(lab.DEFAULT_MODELS, {"decisions": "future-default"}):
                original = lab.replay_record(path)
            revised = copy.deepcopy(manifest["requests"][0]["rubric"])
            revised["questions"]["category"]["acceptable"] = ["unknown"]
            alternative = lab.replay_record(path, overrides={"version": "editorial-2", "requests": {"mixed": revised}})
            self.assertEqual(original["accuracy_on_valid_answers"], 1.)
            self.assertLess(alternative["accuracy_on_valid_answers"], 1.)
            lab.write_evaluation(directory / "evaluation-2.json", alternative)
            self.assertEqual(path.read_bytes(), original_bytes)
            self.assertEqual(lab.replay_record(path)["accuracy_on_valid_answers"], 1.)
            # Cached evaluation edits are never trusted as inference evidence.
            (directory / "evaluation.json").write_text('{"accuracy_on_valid_answers": 0}')
            self.assertEqual(lab.replay_record(path)["accuracy_on_valid_answers"], 1.)
            with self.assertRaises(lab.ApiLabError):
                lab.write_record(directory, record)

    def test_tampered_raw_request_response_or_provenance_is_detected(self):
        manifest = self.mixed()
        record = lab.build_record(manifest, lab.synthetic_entries(manifest), provenance="synthetic")
        with tempfile.TemporaryDirectory() as parent:
            path = Path(parent) / "record.json"
            for field in ("body", "response", "provenance"):
                changed = copy.deepcopy(record)
                if field == "body":
                    changed["manifest"]["requests"][0]["body"]["input"] = "changed"
                elif field == "response":
                    changed["responses"][0]["response"]["answers"][1]["probability"] = 0.
                else:
                    changed["provenance"] = "imported"
                path.write_text(json.dumps(changed))
                with self.subTest(field=field), self.assertRaises(lab.ApiLabError):
                    lab.replay_record(path)

    def test_malformed_json_and_unsafe_evidence_names(self):
        with tempfile.TemporaryDirectory() as parent:
            path = Path(parent) / "bad.json"
            for text in ('{"x": 1, "x": 2}', '{"x": NaN}', '{"x": 1e999}'):
                path.write_text(text)
                with self.assertRaises(lab.ApiLabError):
                    lab.read_json(path)
        manifest = self.manifest("visual-criteria", "jev", limit=1)
        manifest["requests"][0]["id"] = "../../escape"
        manifest.pop("manifest_digest"); manifest["manifest_digest"] = lab.digest(manifest)
        with self.assertRaises(lab.ApiLabError):
            lab.validate_manifest(manifest)

    def test_integrity_preserves_jev_option_order(self):
        body = {"criteria": {"A": "first", "B": "second"}}
        reverse = {"criteria": {"B": "second", "A": "first"}}
        self.assertNotEqual(lab.digest(body), lab.digest(reverse))
        manifest = self.manifest("rule-compile", "jev", limit=1)
        record = lab.build_record(manifest, lab.synthetic_entries(manifest), provenance="synthetic")
        with tempfile.TemporaryDirectory() as parent:
            path = lab.write_record(Path(parent) / "run", record)
            changed = json.loads(path.read_text())
            q = next(iter(changed["manifest"]["requests"][0]["body"]["questions"].values()))
            q["criteria"] = dict(reversed(list(q["criteria"].items())))
            path.write_text(json.dumps(changed))
            with self.assertRaises(lab.ApiLabError):
                lab.replay_record(path)

    def test_asset_keys_or_reference_prefixes_do_not_count_as_image_references(self):
        manifest = self.manifest("visual-criteria", "jev", limit=1)
        request = manifest["requests"][0]
        body = copy.deepcopy(request["body"])
        asset = next(iter(body["assets"].values()))
        body["assets"]["relation"] = copy.deepcopy(asset)  # Only a question-map key.
        with self.assertRaises(lab.ApiLabError):
            lab._check_native(body, request["required_headers"], "jev")
        body = copy.deepcopy(request["body"])
        body["assets"]["t00"] = copy.deepcopy(asset)  # Only a prefix of t001.
        with self.assertRaises(lab.ApiLabError):
            lab._check_native(body, request["required_headers"], "jev")

    def test_real_cli_prepare_import_replay_and_offline_network_guard(self):
        result = subprocess.run([sys.executable, "-m", "decision_lab", "api-lab", "prepare",
                                 "--experiment", "probability", "--route", "decisions", "--limit", "1"],
                                cwd=ROOT, check=True, capture_output=True, text=True)
        manifest = json.loads(result.stdout)
        with tempfile.TemporaryDirectory() as parent:
            parent = Path(parent)
            mpath, rpath = parent / "manifest.json", parent / "responses.json"
            mpath.write_text(json.dumps(manifest))
            rpath.write_text(json.dumps({"schema": lab.RESPONSE_VERSION, "synthetic": True,
                                        "responses": lab.synthetic_entries(manifest)}))
            with patch.object(socket, "create_connection", side_effect=AssertionError("offline command used network")), redirect_stdout(io.StringIO()):
                self.assertEqual(main(["api-lab", "import", "--manifest", str(mpath), "--responses", str(rpath),
                                       "--run-dir", str(parent / "imported")]), 0)
                self.assertEqual(main(["api-lab", "replay", str(parent / "imported")]), 0)
            record = lab._checked_record(parent / "imported")
            self.assertEqual(record["provenance"], "imported")
            self.assertIs(record["synthetic"], True)
            self.assertIs(record["live_verified"], False)

    def test_native_cli_prepare_import_ledger_replay_loop(self):
        account = "a" * 32
        for route in ("clef-flash", "clef", "openrouter-decisions"):
            with self.subTest(route=route), tempfile.TemporaryDirectory() as parent:
                parent = Path(parent)
                command = [sys.executable, "-m", "decision_lab", "api-lab", "prepare",
                           "--experiment", "probability", "--route", route, "--limit", "1"]
                if route in lab.CLOUDFLARE_ROUTES:
                    command.extend(["--account-id", account])
                prepared = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
                manifest = json.loads(prepared.stdout)
                self.assertEqual(manifest["route"], route)
                self.assertEqual(manifest["requests"][0]["body"]["model"], manifest["model"])
                mpath = parent / "manifest.json"
                mpath.write_text(json.dumps(manifest))
                rpath = parent / "responses.json"
                rpath.write_text(json.dumps({
                    "schema": lab.RESPONSE_VERSION,
                    "synthetic": True,
                    "responses": lab.synthetic_entries(manifest),
                }))
                run = parent / "imported"
                import_output, ledger_output = io.StringIO(), io.StringIO()
                with patch.object(socket, "create_connection",
                                  side_effect=AssertionError("offline command used network")):
                    with redirect_stdout(import_output):
                        self.assertEqual(main(["api-lab", "import", "--manifest", str(mpath),
                                               "--responses", str(rpath), "--run-dir", str(run)]), 0)
                    with redirect_stdout(ledger_output):
                        self.assertEqual(main(["research", "ledger", str(run)]), 0)
                    ledger_view = json.loads(ledger_output.getvalue())
                    output = io.StringIO()
                    with redirect_stdout(output):
                        self.assertEqual(main(["api-lab", "replay", str(run)]), 0)
                    replay = json.loads(output.getvalue())
                self.assertEqual(ledger_view["route"], route)
                self.assertEqual(ledger_view["requested_model"], manifest["model"])
                self.assertEqual(ledger_view["trials"][0]["outcome"], "ok")
                self.assertEqual(replay["coverage"]["ok"], replay["coverage"]["expected_questions"])
                self.assertFalse(replay["live_verified"])


if __name__ == "__main__":
    unittest.main()
