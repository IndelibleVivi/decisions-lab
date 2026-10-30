"""Offline round-trip, leakage boundaries, and retained native evidence checks."""
import base64
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from decision_lab.live import TransportResponse

from decision_lab import api_lab as al
from decision_lab import collection, evidence
from decision_lab import evidence_workflow as ew


def fixture(workflow, choose=None, *, provenance="synthetic", marker=None):
    manifest = ew.prepare_round(workflow)
    entries = al.oracle_entries(manifest)
    plans = {p["id"]: p for p in workflow["planned"]}
    scenarios = {s["id"]: s for s in workflow["suite"]["scenarios"]}
    for request, entry in zip(manifest["requests"], entries):
        body = request["body"]
        visible = json.loads(body.get("input", body.get("state")))
        plan = plans[request["trial"]["unit_id"]]
        action = (choose(visible, plan) if choose else
                  evidence.choose_action(scenarios[plan["scenario_id"]], visible, "optimal"))
        answers = entry["response"].get("result", entry["response"])["answers"]
        answer = answers[0] if isinstance(answers, list) else answers["action"]
        answer["choice"] = action
        if isinstance(answer["probabilities"], list):
            for item in answer["probabilities"]:
                item["probability"] = float(item["value"] == action)
        else:
            answer["probabilities"] = {k: float(k == action) for k in answer["probabilities"]}
    return al.build_record(manifest, entries, provenance=provenance, imported_synthetic=marker)


def collected(record, *, repeats=1):
    manifest = record["manifest"]
    attempts = []
    for entry in record["responses"]:
        for number in range(repeats):
            payload = entry["response"]
            attempts.append({"request_id": entry["request_id"], "attempt": number,
                "state": "ok", "delivery": "response_received", "parse_status": "parsed",
                "http_status": 200, "parsed": payload,
                "raw_body_base64": base64.b64encode(json.dumps(payload).encode()).decode(),
                "elapsed_ms": 10, "usage": {"input_tokens": 7, "output_tokens": 3},
                "cost": {"amount": .01, "currency": "USD"}})
    value = {"schema": collection.SCHEMA, "plan": collection.api_plan(manifest),
             "order": [r["id"] for r in manifest["requests"]], "attempts": attempts,
             "provenance": "collector", "synthetic": False, "live_verified": False, "state": "settled"}
    return ew._seal(value)


class EvidenceWorkflowTests(unittest.TestCase):
    def suite(self, ids=None):
        suite = evidence.build_suite()
        if ids:
            suite["scenarios"] = [s for s in suite["scenarios"] if s["id"] in ids]
        return suite

    def xor(self, route="decisions"):
        return ew.start(self.suite(["xor-complement"]), route=route)

    def test_native_rounds_reveal_then_terminal_and_reload(self):
        for route in ("decisions", "jev"):
            with self.subTest(route=route):
                workflow = self.xor(route)
                initial = copy.deepcopy(workflow)
                for turn in range(3):
                    manifest = ew.prepare_round(workflow)
                    self.assertEqual(len(manifest["requests"]), 4)
                    for request in manifest["requests"]:
                        native = al.native_questions(request["body"], route)["action"]
                        self.assertIn("choices" if route == "decisions" else "criteria", native)
                        visible = json.loads(request["body"].get("input", request["body"].get("state")))
                        self.assertEqual(len(visible["history"]), turn)
                        self.assertNotIn("world_id", visible)
                    workflow = ew.apply_round(workflow, fixture(workflow))
                self.assertEqual(initial["rounds"], [])
                self.assertIsNone(ew.prepare_round(workflow))
                result = ew.report(workflow)
                self.assertEqual(result["summary"]["total_loss"], 8)
                self.assertEqual(result["native"]["turns"], 3)
                self.assertEqual(result["native"]["request_count"], 12)
                self.assertIsNone(result["native"]["usage"])
                self.assertTrue(result["synthetic"])
                self.assertFalse(result["live_verified"])
                self.assertTrue(all(len(r["native_requests"]) == 3 for r in result["episodes"]))
                self.assertEqual(evidence.replay(result["run"])["summary"]["total_loss"], result["summary"]["total_loss"])
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "workflow.json"
                    path.write_text(json.dumps(workflow))
                    self.assertEqual(ew.report(path), result)
                with self.assertRaisesRegex(ValueError, "terminal"):
                    ew.apply_round(workflow, fixture(initial))

    def test_identical_visible_histories_have_identical_native_body(self):
        workflow = self.xor()
        bodies = [r["body"] for r in ew.prepare_round(workflow)["requests"]]
        self.assertTrue(all(b == bodies[0] for b in bodies))
        workflow = ew.apply_round(workflow, fixture(workflow))
        grouped = {}
        for request in ew.prepare_round(workflow)["requests"]:
            body = request["body"]
            history = json.loads(body["input"])["history"]
            key = json.dumps(history)
            self.assertEqual(grouped.setdefault(key, body), body)
            self.assertNotIn(request["trial"]["unit_id"], json.dumps(body))
        self.assertEqual(len(grouped), 2)

    def test_stale_reuse_tampering_foreign_manifest_rejected(self):
        workflow = self.xor()
        source = fixture(workflow)
        advanced = ew.apply_round(workflow, source)
        with self.assertRaisesRegex(ValueError, "current round"):
            ew.apply_round(advanced, source)
        changed = copy.deepcopy(advanced)
        changed["rounds"][0]["responses"][0]["response"]["model"] = "edited"
        with self.assertRaisesRegex(ValueError, "digest"):
            ew.report(changed)
        ew._seal(changed)
        with self.assertRaisesRegex(ValueError, "digest"):
            ew.report(changed)
        foreign = fixture(ew.start(self.suite(["key-evidence"]), route="decisions"))
        with self.assertRaisesRegex(ValueError, "current round"):
            ew.apply_round(workflow, foreign)
        changed = copy.deepcopy(advanced)
        changed["state"] = {}
        ew._seal(changed)
        with self.assertRaisesRegex(ValueError, "derived state"):
            ew.report(changed)

    def test_partial_missing_and_uncertain_are_atomic_and_report_full_missing(self):
        workflow = self.xor()
        before = copy.deepcopy(workflow)
        source = fixture(workflow)
        source["responses"].pop()
        ew._seal(source)
        with self.assertRaisesRegex(ValueError, "missing responses"):
            ew.apply_round(workflow, source)
        self.assertEqual(workflow, before)
        source = fixture(workflow)
        source["responses"][0]["response"]["answers"] = []
        ew._seal(source)
        with self.assertRaisesRegex(ValueError, "missing native answer"):
            ew.apply_round(workflow, source)
        source = collected(fixture(workflow))
        source["attempts"][0].update(state="transport_error", delivery="uncertain", parsed=None,
                                             raw_body_base64=None, parse_status="not_received")
        ew._seal(source)
        with self.assertRaisesRegex(ValueError, "uncertain"):
            ew.apply_round(workflow, source)
        result = ew.report(workflow)
        self.assertEqual(result["summary"]["planned"], 4)
        self.assertEqual(result["summary"]["missing"], 4)
        self.assertEqual(result["summary"]["total_loss"], 48)
        self.assertIsNone(result["synthetic"])
        self.assertEqual(workflow, before)

    def test_unknown_refusal_error_and_business_abstain_are_distinct(self):
        workflow = self.xor()
        source = fixture(workflow, lambda v, p: "abstain")
        source["responses"][0]["response"]["answers"][0] = {"name": "action", "type": "refusal"}
        source["responses"][1].update(error="transport failed", response=None)
        answer = source["responses"][2]["response"]["answers"][0]
        answer["choice"] = "unknown"
        for probability in answer["probabilities"]:
            probability["probability"] = float(probability["value"] == "unknown")
        ew._seal(source)
        result = ew.report(ew.apply_round(workflow, source))
        self.assertEqual(result["summary"]["failure_statuses"], {"unknown": 1, "refusal": 1, "error": 1, "missing": 0})
        self.assertEqual(result["summary"]["abstained"], 1)
        self.assertEqual(result["summary"]["committed"], 0)
        self.assertEqual(result["summary"]["api_failed"], 3)
        self.assertEqual(result["summary"]["pending"], 0)
        self.assertEqual(result["summary"]["commit_coverage"], 0)
        self.assertEqual(result["summary"]["decision_coverage"], .25)
        self.assertEqual(result["summary"]["total_loss"], 39)
        self.assertTrue(all(r["expected_regret"] is None for r in result["episodes"]))

    def test_collector_accounting_counts_requests_once_attempts_all(self):
        workflow = self.xor()
        source = collected(fixture(workflow), repeats=2)
        advanced = ew.apply_round(workflow, source)
        native = ew.report(advanced)["native"]
        self.assertEqual(native["request_count"], 4)
        self.assertEqual(native["attempt_count"], 8)
        self.assertEqual(native["latency_ms"], 80)
        self.assertEqual(native["usage"], {"input_tokens": 56, "output_tokens": 24})
        self.assertEqual(native["cost"], {"amount": .08, "currency": "USD"})
        self.assertFalse(native["live_verified"])
        self.assertFalse(ew.report(advanced)["synthetic"])
        source["attempts"][0]["parsed"] = {}
        ew._seal(source)
        with self.assertRaisesRegex(ValueError, "retained bytes"):
            ew.apply_round(workflow, source)

    def test_nested_native_usage_survives_collector_replay(self):
        workflow = self.xor()
        source = collected(fixture(workflow), repeats=2)
        for attempt in source["attempts"]:
            attempt["usage"]["input_tokens_details"] = {"cached_tokens": 2, "cache_write_tokens": 0}
        ew._seal(source)
        usage = ew.report(ew.apply_round(workflow, source))["native"]["usage"]
        self.assertEqual(usage, {"input_tokens": 56, "output_tokens": 24,
                                 "input_tokens_details": {"cached_tokens": 16, "cache_write_tokens": 0}})
        source["attempts"][0]["usage"]["input_tokens_details"]["cached_tokens"] = None
        ew._seal(source)
        self.assertIsNone(ew.report(ew.apply_round(workflow, source))["native"]["usage"])

    def test_imported_unknown_cost_and_provenance_stay_unknown(self):
        workflow = self.xor()
        source = fixture(workflow, provenance="imported")
        result = ew.report(ew.apply_round(workflow, source))
        self.assertIsNone(result["synthetic"])
        self.assertIsNone(result["native"]["attempt_count"])
        self.assertIsNone(result["native"]["cost"])
        self.assertEqual({m["provenance"] for m in result["native"]["requests"]}, {"imported"})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "record.json"
            path.write_text(json.dumps(source))
            self.assertEqual(ew.apply_round(workflow, path), ew.apply_round(workflow, source))

    def test_pair_baseline_full_missing_denominator_and_suite_identity(self):
        suite = self.suite(["xor-complement"])
        baseline = evidence.run_suite(suite, "stop")
        workflow = ew.start(suite, route="decisions")
        comparison = ew.compare(baseline, workflow)
        self.assertEqual(comparison["summary"]["planned"], 4)
        self.assertEqual(comparison["summary"]["fully_observed_pairs"], 0)
        self.assertEqual(comparison["summary"]["right_missing"], 4)
        self.assertEqual(comparison["summary"]["total_loss"]["right"], 12)
        for _ in range(3):
            workflow = ew.apply_round(workflow, fixture(workflow))
        comparison = ew.compare(baseline, workflow)
        self.assertEqual(comparison["summary"]["fully_observed_pairs"], 4)
        self.assertEqual(comparison["summary"]["total_loss"]["delta_right_minus_left"], -1)
        self.assertEqual(set(comparison["families"]), {"xor-complement"})
        self.assertIsNone(comparison["interval"])
        altered = ew.start(suite, route="decisions", replicates=2)
        with self.assertRaisesRegex(ValueError, "planned identities"):
            ew.compare(baseline, altered)
        altered = self.suite(["xor-complement"])
        altered["scenarios"][0]["failure_loss"] = 11
        with self.assertRaisesRegex(ValueError, "frozen suite"):
            ew.compare(baseline, ew.start(altered, route="decisions"))

    def test_native_response_accounting_and_synthetic_exclusion(self):
        for route in ("decisions", "jev", "clef"):
            with self.subTest(route=route):
                kwargs = {"account_id": "a" * 32} if route == "clef" else {}
                workflow = ew.start(self.suite(["xor-complement"]), route=route, **kwargs)
                source = fixture(workflow, provenance="imported", marker=False)
                for entry in source["responses"]:
                    raw = entry["response"].get("result", entry["response"])
                    raw.update(usage={"input_tokens": 5}, cost={"amount": .1, "currency": "USD"})
                ew._seal(source)
                native = ew.report(ew.apply_round(workflow, source))["native"]
                self.assertEqual(native["usage"], {"input_tokens": 20})
                self.assertAlmostEqual(native["cost"]["amount"], .4)
                source.update(provenance="synthetic", synthetic=True)
                ew._seal(source)
                native = ew.report(ew.apply_round(workflow, source))["native"]
                self.assertIsNone(native["usage"])
                self.assertIsNone(native["cost"])

    def test_nonuniform_prior_weighting_and_family_equal_aggregation(self):
        suite = self.suite(["uninformative", "robust-stop", "key-evidence"])
        suite["scenarios"][0]["source_family"] = "shared"
        suite["scenarios"][1]["source_family"] = "shared"
        baseline = evidence.run_suite(suite, "stop")
        workflow = ew.start(suite, route="decisions", replicates=1)
        workflow = ew.apply_round(workflow, fixture(workflow, lambda visible, plan:
            "commit:rare" if visible["id"] == "uninformative" else "abstain"))
        result = ew.compare(baseline, workflow)
        uninformative = result["scenarios"]["uninformative"]
        self.assertEqual(uninformative["total_loss"]["delta_right_minus_left"], 0)
        self.assertAlmostEqual(uninformative["prior_weighted_scenario_equal"]["total_loss"]["delta_right_minus_left"], 2.4)
        self.assertNotEqual(result["summary"]["prior_weighted_scenario_equal"],
                            result["summary"]["prior_weighted_family_equal"])
        self.assertEqual(result["summary"]["terminal_decision_pairs"], 6)

    def test_existing_native_writers_and_collector_checkpoint_paths(self):
        workflow = self.xor()
        source = fixture(workflow)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record_path = al.write_record(root / "native", source)
            self.assertEqual(al.replay_record(record_path)["provenance"], "synthetic")
            self.assertEqual(ew.apply_round(workflow, record_path), ew.apply_round(workflow, source))
            replies = iter(source["responses"])
            # Actual collector persistence path, with injected in-process client.
            # The native body is identical across the initial XOR worlds.
            class FakeClient:
                def post_json(self, endpoint, headers, body):
                    return TransportResponse(200, json.dumps(next(replies)["response"]).encode(), 0)
            with patch("socket.create_connection", side_effect=AssertionError("network forbidden")):
                checkpoint = collection.collect(collection.api_plan(source["manifest"]), root / "collector",
                    allow_network=True, max_calls=4, max_questions=4, max_estimated_tokens=100000,
                    client=FakeClient(), credential="synthetic-test-key")
            self.assertEqual(collection.load_collection(root / "collector"), checkpoint)
            by_path = ew.apply_round(workflow, root / "collector")
            self.assertEqual(by_path, ew.apply_round(workflow, checkpoint))
            native = ew.report(by_path)["native"]
            self.assertEqual(native["attempt_count"], 4)
            self.assertEqual(native["call_count"], 4)
            self.assertIsNone(native["cost"])

    def test_demo_body_only_controls_match_core_realized_losses(self):
        suite = self.suite(["xor-complement", "key-evidence", "uninformative"])
        for route in ("decisions", "jev"):
            for policy in evidence.POLICIES:
                with self.subTest(route=route, policy=policy):
                    workflow = ew.demo(suite, route=route, policy=policy)
                    result = ew.report(workflow)
                    baseline = evidence.replay(evidence.run_suite(suite, policy))
                    for key in ("total_loss", "terminal_loss", "query_cost"):
                        self.assertEqual(result["summary"][key], baseline["summary"][key])
                    self.assertIsNone(ew.prepare_round(workflow))
                    self.assertTrue(result["synthetic"])
                    self.assertEqual(result["summary"]["decision_coverage"], 1)
                    self.assertTrue(all(r["expected_regret"] is None for r in result["episodes"]))

    def test_comparison_preserves_round_source_claims(self):
        workflow = ew.demo(self.suite(["key-evidence"]), route="jev")
        result = ew.compare(evidence.run_suite(workflow["suite"]), workflow)
        origin = result["evidence"]["right"]
        self.assertEqual(origin["route"], "jev")
        self.assertTrue(origin["synthetic"])
        self.assertEqual(len(origin["source_records"]), 2)
        self.assertTrue(all(row["provenance"] == "synthetic" for row in origin["source_records"]))
        self.assertFalse(origin["live_verified"])

    def test_full_suite_terminates_and_supported_native_configuration_only(self):
        workflow = ew.start(self.suite(), route="decisions", replicates=2)
        turns = 0
        while ew.prepare_round(workflow) is not None:
            workflow = ew.apply_round(workflow, fixture(workflow))
            turns += 1
            self.assertLessEqual(turns, 3)
        result = ew.report(workflow)
        self.assertEqual(result["summary"]["planned"], 32)
        self.assertEqual(result["summary"]["missing"], 0)
        for route in ("clef", "clef-flash", "openrouter-decisions"):
            with self.subTest(route=route):
                kwargs = {"account_id": "a" * 32} if route in al.CLOUDFLARE_ROUTES else {}
                workflow = ew.start(self.suite(["xor-complement"]), route=route, **kwargs)
                manifest = ew.prepare_round(workflow)
                self.assertEqual(manifest["route"], route)
                self.assertFalse(manifest["live_verified"])
                ew.apply_round(workflow, fixture(workflow))


if __name__ == "__main__":
    unittest.main()
