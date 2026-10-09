"""Route contract + normalization tests, written against the documented
shapes (docs verified by the coordinator on 2026-10-09; no live calls).

Covers: exact request fields/endpoint, doc-shaped positive responses,
OpenAI refusal kept distinct, TypeSafe missing-choice as an ERROR (never
``unknown``), duplicate/foreign probabilities rejected, native confidence
retained, and the structural no-label-leak guard.
"""

from __future__ import annotations

import json
import unittest

from decision_lab.cases import parse_case
from decision_lab.routes import (
    OFFERED_OPTIONS,
    OUTCOME_ERROR,
    OUTCOME_OK,
    OUTCOME_REFUSAL,
    OUTCOME_UNKNOWN,
    assert_request_is_clean,
    build_request,
    get_route,
    protocol_profiles,
)


def _case(**over):
    base = {
        "id": "case-xyz",
        "source_group": "grp-unique-alpha",
        "split": "dev",
        "task": {"document": "doc body", "claim": "a claim", "source_ref": "https://x.invalid"},
        "acceptable": ["compare_contract", "inspect_source"],
        "rationale": "rationale-unique-text-42",
    }
    base.update(over)
    return parse_case(base)


def _full_dist(selected, mass=0.6):
    others = [o for o in OFFERED_OPTIONS if o != selected]
    rest = (1.0 - mass) / len(others)
    d = {o: rest for o in others}
    d[selected] = mass
    return d


def _jev_answer(choice, conf=0.5, probs=None):
    return {
        "model": "jev-1.13.0",
        "answers": {
            "next_action": {
                "type": "choice",
                "choice": choice,
                "probabilities": probs if probs is not None else _full_dist(choice),
                "confidence": conf,
            }
        },
    }


def _dec_answer(choice, conf=0.5, probs=None):
    dist = probs if probs is not None else _full_dist(choice)
    return {
        "model": "gpt-6-luna",
        "answers": [
            {
                "type": "choice",
                "name": "next_action",
                "choice": choice,
                "probabilities": [
                    {"value": k, "probability": v} for k, v in dist.items()
                ],
                "confidence": conf,
            }
        ],
    }


class TestRequestShape(unittest.TestCase):
    def test_jev_request_matches_docs(self):
        body = build_request("jev", _case())
        self.assertEqual(set(body), {"model", "state", "questions"})
        self.assertEqual(body["model"], "jev-1.13.0")
        self.assertNotIn("request_id", body)
        q = body["questions"]["next_action"]
        self.assertEqual(q["type"], "choice")
        self.assertEqual(q["instructions"], "What is the single best next reading/checking action?")
        self.assertEqual(set(q["criteria"]), set(OFFERED_OPTIONS))
        for opt in OFFERED_OPTIONS:
            self.assertTrue(q["criteria"][opt].strip())

    def test_decisions_request_matches_docs(self):
        body = build_request("decisions", _case())
        self.assertEqual(set(body), {"model", "input", "questions"})
        self.assertEqual(body["model"], "gpt-6-luna")
        self.assertIsInstance(body["input"], str)
        self.assertNotIn("decision", body)
        self.assertNotIn("metadata", body)
        q = body["questions"][0]
        self.assertEqual((q["type"], q["name"]), ("choice", "next_action"))
        self.assertEqual([c["value"] for c in q["choices"]], list(OFFERED_OPTIONS))
        for c in q["choices"]:
            self.assertTrue(c["description"].strip())

    def test_endpoints_are_exact(self):
        self.assertEqual(get_route("jev").endpoint, "https://api.typesafe.ai/v1/systemone")
        self.assertEqual(get_route("decisions").endpoint, "https://api.openai.com/v1/decisions")

    def test_native_shapes_differ(self):
        jev = build_request("jev", _case())
        dec = build_request("decisions", _case())
        self.assertNotEqual(set(jev), set(dec))

    def test_only_task_input_is_sent(self):
        blob = json.dumps(build_request("decisions", _case()), ensure_ascii=False)
        self.assertNotIn("rationale-unique-text-42", blob)
        self.assertNotIn("grp-unique-alpha", blob)
        self.assertNotIn("case-xyz", blob)

    def test_label_leak_is_caught_structurally(self):
        c = _case()
        with self.assertRaises(AssertionError):
            assert_request_is_clean({"acceptable": ["inspect_source"]}, c)
        with self.assertRaises(AssertionError):
            assert_request_is_clean({"id": c.id}, c)
        with self.assertRaises(AssertionError):
            assert_request_is_clean({"note": c.rationale}, c)
        with self.assertRaises(AssertionError):
            assert_request_is_clean({"answers": ["compare_contract", "inspect_source"]}, c)

    def test_short_source_group_substring_is_not_falsely_flagged(self):
        c = _case(source_group="app", task={
            "document": "The app retries by default.", "claim": "", "source_ref": "",
        })
        build_request("jev", c)  # must not raise


class TestNormalizeJev(unittest.TestCase):
    def setUp(self):
        self.route = get_route("jev")

    def test_ok_choice(self):
        r = self.route.normalize(200, _jev_answer("inspect_source", conf=0.7))
        self.assertEqual(r.outcome, OUTCOME_OK)
        self.assertEqual(r.action, "inspect_source")
        self.assertEqual(r.confidence, 0.7)
        self.assertEqual(r.model, "jev-1.13.0")
        self.assertAlmostEqual(sum(r.probabilities.values()), 1.0)

    def test_native_confidence_kept_separately_from_maxp(self):
        r = self.route.normalize(200, _jev_answer("compare_contract", conf=0.25))
        self.assertEqual(r.confidence, 0.25)
        self.assertNotEqual(r.confidence, max(r.probabilities.values()))

    def test_explicit_unknown_is_ok_answer(self):
        r = self.route.normalize(200, _jev_answer("unknown"))
        self.assertEqual(r.outcome, OUTCOME_UNKNOWN)
        self.assertEqual(r.action, "unknown")

    def test_missing_choice_is_error_not_unknown(self):
        payload = _jev_answer("unknown")
        del payload["answers"]["next_action"]["choice"]
        r = self.route.normalize(200, payload)
        self.assertEqual(r.outcome, OUTCOME_ERROR)
        self.assertNotEqual(r.outcome, OUTCOME_UNKNOWN)

    def test_missing_confidence_is_error(self):
        payload = _jev_answer("inspect_source")
        del payload["answers"]["next_action"]["confidence"]
        self.assertEqual(self.route.normalize(200, payload).outcome, OUTCOME_ERROR)

    def test_no_refusal_field_is_honored(self):
        r = self.route.normalize(200, {"refused": True, "refusal": "policy"})
        self.assertEqual(r.outcome, OUTCOME_ERROR)

    def test_http_error_is_not_unknown(self):
        self.assertEqual(self.route.normalize(500, {"error": "boom"}).error_kind, "http_500")

    def test_foreign_option_key_rejected(self):
        probs = _full_dist("inspect_source")
        probs["make_coffee"] = 0.0
        r = self.route.normalize(200, _jev_answer("inspect_source", probs=probs))
        self.assertEqual(r.outcome, OUTCOME_ERROR)

    def test_nonfinite_probability_rejected(self):
        probs = _full_dist("inspect_source")
        probs["inspect_source"] = float("nan")
        self.assertEqual(
            self.route.normalize(200, _jev_answer("inspect_source", probs=probs)).outcome,
            OUTCOME_ERROR,
        )

    def test_bool_probability_rejected(self):
        probs = _full_dist("inspect_source")
        probs["inspect_source"] = True
        self.assertEqual(
            self.route.normalize(200, _jev_answer("inspect_source", probs=probs)).outcome,
            OUTCOME_ERROR,
        )

    def test_sum_not_one_rejected(self):
        probs = {o: 0.1 for o in OFFERED_OPTIONS}
        self.assertEqual(
            self.route.normalize(200, _jev_answer("inspect_source", probs=probs)).outcome,
            OUTCOME_ERROR,
        )

    def test_selected_not_argmax_rejected(self):
        probs = _full_dist("compare_contract")
        probs["inspect_source"] = 0.05
        r = self.route.normalize(200, _jev_answer("inspect_source", probs=probs))
        self.assertEqual(r.outcome, OUTCOME_ERROR)

    def test_non_object_payload_is_error(self):
        self.assertEqual(self.route.normalize(200, ["nope"]).outcome, OUTCOME_ERROR)


class TestNormalizeDecisions(unittest.TestCase):
    def setUp(self):
        self.route = get_route("decisions")

    def test_ok(self):
        r = self.route.normalize(200, _dec_answer("read_in_context", conf=0.4))
        self.assertEqual(r.outcome, OUTCOME_OK)
        self.assertEqual(r.action, "read_in_context")
        self.assertEqual(r.confidence, 0.4)

    def test_unknown(self):
        self.assertEqual(self.route.normalize(200, _dec_answer("unknown")).outcome, OUTCOME_UNKNOWN)

    def test_refusal_is_its_own_answer_type(self):
        payload = {"answers": [
            {"type": "refusal", "name": "next_action", "refusal": "cannot comply"}
        ]}
        r = self.route.normalize(200, payload)
        self.assertEqual(r.outcome, OUTCOME_REFUSAL)
        self.assertEqual(r.refusal_reason, "cannot comply")
        self.assertIsNone(r.action)

    def test_top_level_refusal_is_not_honored(self):
        r = self.route.normalize(200, {"refusal": "cannot comply"})
        self.assertEqual(r.outcome, OUTCOME_ERROR)

    def test_error_status(self):
        self.assertEqual(self.route.normalize(429, {"error": "rate"}).error_kind, "http_429")

    def test_probabilities_preserved_by_value(self):
        probs = {"inspect_source": 0.42, "read_in_context": 0.18, "compare_contract": 0.2,
                 "needs_more_context": 0.1, "unknown": 0.1}
        r = self.route.normalize(200, _dec_answer("inspect_source", probs=probs))
        self.assertEqual(r.probabilities["inspect_source"], 0.42)
        self.assertEqual(r.probabilities["read_in_context"], 0.18)

    def test_duplicate_array_values_rejected(self):
        payload = _dec_answer("inspect_source")
        payload["answers"][0]["probabilities"].append(
            {"value": "inspect_source", "probability": 0.0}
        )
        self.assertEqual(self.route.normalize(200, payload).outcome, OUTCOME_ERROR)

    def test_missing_name_is_error(self):
        payload = _dec_answer("inspect_source")
        payload["answers"][0].pop("name")
        self.assertEqual(self.route.normalize(200, payload).outcome, OUTCOME_ERROR)

    def test_missing_choice_is_error_not_unknown(self):
        payload = _dec_answer("unknown")
        payload["answers"][0].pop("choice")
        self.assertEqual(self.route.normalize(200, payload).outcome, OUTCOME_ERROR)

    def test_four_outcomes_are_distinct(self):
        ok = self.route.normalize(200, _dec_answer("inspect_source"))
        unk = self.route.normalize(200, _dec_answer("unknown"))
        ref = self.route.normalize(200, {"answers": [
            {"type": "refusal", "name": "next_action", "refusal": "no"}]})
        err = self.route.normalize(503, {"error": "down"})
        self.assertEqual(
            {ok.outcome, unk.outcome, ref.outcome, err.outcome},
            {OUTCOME_OK, OUTCOME_UNKNOWN, OUTCOME_REFUSAL, OUTCOME_ERROR},
        )


class TestProvenance(unittest.TestCase):
    def test_profiles_report_docs_verified_not_live(self):
        meta = protocol_profiles()
        self.assertEqual(meta["docs_verified_at"], "2026-10-09")
        self.assertFalse(meta["live_verified"])
        self.assertIn("docs.typesafe.ai/api", meta["routes"]["jev"]["docs_url"])
        self.assertIn("developers.openai.com", meta["routes"]["decisions"]["docs_url"])

    def test_declared_fields_match_behavior(self):
        jev = get_route("jev")
        r = jev.normalize(200, _jev_answer("inspect_source"))
        self.assertEqual(jev.choice_field, "answers.next_action.choice")
        self.assertIsNotNone(r.probabilities)
        dec = get_route("decisions")
        r2 = dec.normalize(200, _dec_answer("inspect_source"))
        self.assertEqual(dec.choice_field, "answers[].choice")
        self.assertIsNotNone(r2.probabilities)


class TestResponseBoundaries(unittest.TestCase):
    def test_confidence_must_be_in_unit_interval(self):
        for key, fixture in (("jev", _jev_answer), ("decisions", _dec_answer)):
            for confidence in (-0.1, 1.1):
                with self.subTest(route=key, confidence=confidence):
                    result = get_route(key).normalize(200, fixture("inspect_source", conf=confidence))
                    self.assertEqual(result.outcome, OUTCOME_ERROR)
            for confidence in (0.0, 1.0):
                with self.subTest(route=key, confidence=confidence):
                    result = get_route(key).normalize(200, fixture("inspect_source", conf=confidence))
                    self.assertEqual(result.outcome, OUTCOME_OK)

    def test_jev_rejects_an_unrequested_answer(self):
        payload = _jev_answer("inspect_source")
        payload["answers"]["other_question"] = dict(payload["answers"]["next_action"])
        self.assertEqual(get_route("jev").normalize(200, payload).outcome, OUTCOME_ERROR)

    def test_decisions_rejects_duplicate_or_unrequested_answers(self):
        for name in ("next_action", "other_question"):
            with self.subTest(name=name):
                payload = _dec_answer("inspect_source")
                payload["answers"].append(dict(payload["answers"][0], name=name))
                self.assertEqual(get_route("decisions").normalize(200, payload).outcome, OUTCOME_ERROR)


if __name__ == "__main__":
    unittest.main()
