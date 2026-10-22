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

    def manifest(self, experiment="probability", route="decisions", ids=None, limit=None):
        rows = lab.select_rows(self.suite, experiment=experiment, case_ids=ids, limit=limit)
        return lab.prepare_payload(self.suite, rows, route=route)

    def mixed(self, route="decisions"):
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
        return lab.prepare_payload(lab.Suite({}, [case]), [case], route=route)

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
            manifest = self.mixed(route)
            results = lab.evaluate(manifest, lab.synthetic_entries(manifest))
            self.assertEqual(results["coverage"]["ok"], 3)
            self.assertEqual(results["accuracy_on_valid_answers"], 1.)
            if route == "jev":
                self.assertEqual(manifest["requests"][0]["body"]["questions"]["severity"]["criteria"],
                                 ["Low severity", "High severity"])

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


if __name__ == "__main__":
    unittest.main()
