"""Record, replay and evaluation tests (part 1)."""

from __future__ import annotations

import dataclasses
import tempfile
import unittest
from pathlib import Path

from decision_lab.cases import Case, Suite, load_suite, parse_case
from decision_lab.record import (
    CaseResult,
    Record,
    RecordError,
    case_digest,
    evaluate,
    load_record,
    run_baseline,
    run_demo,
    suite_digest,
    threshold_coverage,
    write_record,
    route_model_check,
)

REPO = Path(__file__).resolve().parent.parent
SUITE_PATH = REPO / "experiments" / "next-action" / "cases.json"


def _suite() -> Suite:
    return load_suite(SUITE_PATH)


def _result_for(case: Case, *, outcome="ok", action=None, correct=None,
                error_kind=None) -> CaseResult:
    return CaseResult(
        case_id=case.id, source_group=case.source_group, split=case.split,
        digest=case_digest(case), outcome=outcome, action=action,
        probabilities=None, model="m", correct=correct, error_kind=error_kind,
    )


def _dist(selected: str, mass: float = 0.6) -> dict:
    from decision_lab.routes import OFFERED_OPTIONS
    others = [o for o in OFFERED_OPTIONS if o != selected]
    rest = (1.0 - mass) / len(others)
    d = {o: rest for o in others}
    d[selected] = mass
    return d


def _record_for(suite: Suite, results) -> Record:
    return Record(
        provenance="baseline", route="baseline", native_model=None,
        suite_path=str(SUITE_PATH), suite_digest=suite_digest(suite),
        protocol={}, results=results, synthetic=True,
    )


class TestRecordRoundTrip(unittest.TestCase):
    def test_baseline_roundtrip_and_eval(self):
        suite = _suite()
        rec = run_baseline(suite, suite_path=str(SUITE_PATH))
        with tempfile.TemporaryDirectory() as d:
            out = write_record(Path(d) / "run", rec)
            loaded = load_record(out)
            rep = evaluate(loaded, suite, suite_path=str(SUITE_PATH))
        self.assertEqual(rep.total, len(suite.cases))
        self.assertEqual(rep.attempted, rep.total)
        self.assertIsNotNone(rep.accuracy)

    def test_demo_has_wrong_and_unknown(self):
        suite = _suite()
        rec = run_demo(suite, suite_path=str(SUITE_PATH))
        self.assertTrue(rec.synthetic)
        self.assertTrue(any(r.correct is False for r in rec.results))
        self.assertTrue(any(r.outcome == "unknown" for r in rec.results))
        self.assertEqual(len(rec.results), len(suite.cases))
        rep = evaluate(rec, suite, suite_path=str(SUITE_PATH))
        self.assertEqual(rep.unknown, 1)

    def test_baseline_marked_synthetic(self):
        suite = _suite()
        rec = run_baseline(suite, suite_path=str(SUITE_PATH))
        self.assertTrue(rec.synthetic)
        self.assertEqual(rec.provenance, "baseline")

    def test_clobber_refused(self):
        suite = _suite()
        rec = run_baseline(suite, suite_path=str(SUITE_PATH))
        with tempfile.TemporaryDirectory() as d:
            run = Path(d) / "run"
            write_record(run, rec)
            with self.assertRaises(RecordError):
                write_record(run, rec)

    def test_refuse_write_into_source_tree(self):
        suite = _suite()
        rec = run_baseline(suite, suite_path=str(SUITE_PATH))
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(RecordError):
                write_record(Path(d) / "catalog" / "run", rec)


class TestReplayGuards(unittest.TestCase):
    def test_missing_case_detected(self):
        suite = _suite()
        results = [_result_for(c, action=c.acceptable[0], correct=True) for c in suite.cases[:-1]]
        with self.assertRaises(RecordError) as ctx:
            evaluate(_record_for(suite, results), suite, suite_path=str(SUITE_PATH))
        self.assertIn("missing", str(ctx.exception))

    def test_duplicate_case_detected(self):
        suite = _suite()
        results = [_result_for(c, action=c.acceptable[0], correct=True) for c in suite.cases]
        results.append(results[0])
        with self.assertRaises(RecordError) as ctx:
            evaluate(_record_for(suite, results), suite, suite_path=str(SUITE_PATH))
        self.assertIn("duplicate", str(ctx.exception))

    def test_foreign_case_detected(self):
        suite = _suite()
        results = [_result_for(c, action=c.acceptable[0], correct=True) for c in suite.cases]
        results.append(
            CaseResult(case_id="foreign-123", source_group="x", split="dev", digest="sha256:z",
                       outcome="ok", action="inspect_source", probabilities=None,
                       model="m", correct=True)
        )
        with self.assertRaises(RecordError) as ctx:
            evaluate(_record_for(suite, results), suite, suite_path=str(SUITE_PATH))
        self.assertIn("foreign", str(ctx.exception))

    def test_digest_mismatch_detected(self):
        suite = _suite()
        results = [_result_for(c, action=c.acceptable[0], correct=True) for c in suite.cases]
        results[0] = dataclasses.replace(results[0], digest="sha256:deadbeef")
        with self.assertRaises(RecordError) as ctx:
            evaluate(_record_for(suite, results), suite, suite_path=str(SUITE_PATH))
        self.assertIn("differs", str(ctx.exception))

    def test_suite_path_mismatch_detected(self):
        suite = _suite()
        results = [_result_for(c, action=c.acceptable[0], correct=True) for c in suite.cases]
        rec = _record_for(suite, results)
        rec.suite_path = "/some/other/cases.json"
        with self.assertRaises(RecordError):
            evaluate(rec, suite, suite_path=str(SUITE_PATH))

    def test_suite_content_change_detected(self):
        suite = _suite()
        results = [_result_for(c, action=c.acceptable[0], correct=True) for c in suite.cases]
        rec = _record_for(suite, results)
        c0 = suite.cases[0]
        suite.cases[0] = parse_case(
            {
                "id": c0.id, "source_group": c0.source_group, "split": c0.split,
                "task": {"document": "CHANGED TEXT", "claim": "", "source_ref": ""},
                "acceptable": c0.acceptable, "rationale": "changed",
            }
        )
        with self.assertRaises(RecordError) as ctx:
            evaluate(rec, suite, suite_path=str(SUITE_PATH))
        self.assertIn("digest", str(ctx.exception))


class TestCoverageAndStats(unittest.TestCase):
    def test_unknown_does_not_count_as_correct(self):
        suite = _suite()
        results = [_result_for(c, action=c.acceptable[0], correct=True) for c in suite.cases]
        results[0] = _result_for(suite.cases[0], outcome="unknown", action="unknown", correct=None)
        rep = evaluate(_record_for(suite, results), suite, suite_path=str(SUITE_PATH))
        self.assertEqual(rep.unknown, 1)
        self.assertEqual(rep.answered, len(suite.cases) - 1)
        self.assertEqual(rep.correct, len(suite.cases) - 1)

    def test_error_counted_as_attempted_not_correct(self):
        suite = _suite()
        results = [_result_for(c, action=c.acceptable[0], correct=True) for c in suite.cases]
        results[0] = _result_for(suite.cases[0], outcome="error", action=None,
                                 correct=None, error_kind="transport")
        rep = evaluate(_record_for(suite, results), suite, suite_path=str(SUITE_PATH))
        self.assertEqual(rep.errors, 1)
        self.assertEqual(rep.attempted, rep.total)
        self.assertEqual(len(rep.errors_detail), 1)

    def test_threshold_requires_probabilities(self):
        suite = _suite()
        results = [_result_for(c, action=c.acceptable[0], correct=True) for c in suite.cases]
        cov = threshold_coverage(_record_for(suite, results), threshold=0.5)
        self.assertEqual(cov["covered"], 0)
        self.assertIsNone(cov["accuracy"])

    def test_threshold_with_probabilities(self):
        suite = _suite()
        results = []
        for i, c in enumerate(suite.cases):
            r = _result_for(c, action=c.acceptable[0], correct=True)
            r.probabilities = _dist(c.acceptable[0], 0.9) if i % 2 == 0 else _dist(c.acceptable[0], 0.2)
            results.append(r)
        cov = threshold_coverage(_record_for(suite, results), threshold=0.5)
        expected = (len(suite.cases) + 1) // 2
        self.assertEqual(cov["covered"], expected)
        self.assertEqual(cov["accuracy"], 1.0)

    def test_threshold_rejects_nonfinite(self):
        suite = _suite()
        results = [_result_for(c, action=c.acceptable[0], correct=True) for c in suite.cases]
        rec = _record_for(suite, results)
        for bad in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(RecordError):
                threshold_coverage(rec, threshold=bad)

    def test_usage_cost_null_when_absent(self):
        suite = _suite()
        rec = run_baseline(suite, suite_path=str(SUITE_PATH))
        for r in rec.results:
            self.assertIsNone(r.usage)
            self.assertIsNone(r.cost)

    def test_route_model_check(self):
        suite = _suite()
        rec = run_baseline(suite, suite_path=str(SUITE_PATH))
        with self.assertRaises(RecordError):
            route_model_check(rec, "jev")


class TestRecordIntegrity(unittest.TestCase):
    """A corrupted record must not be countable as correct."""

    def test_ok_requires_positive_action(self):
        suite = _suite()
        results = [_result_for(c, action=c.acceptable[0], correct=True) for c in suite.cases]
        results[0] = _result_for(suite.cases[0], outcome="ok", action=None, correct=True)
        with self.assertRaises(RecordError):
            evaluate(_record_for(suite, results), suite, suite_path=str(SUITE_PATH))

    def test_ok_with_unknown_action_rejected(self):
        suite = _suite()
        results = [_result_for(c, action=c.acceptable[0], correct=True) for c in suite.cases]
        results[0] = _result_for(suite.cases[0], outcome="ok", action="unknown", correct=True)
        with self.assertRaises(RecordError):
            evaluate(_record_for(suite, results), suite, suite_path=str(SUITE_PATH))

    def test_unknown_marked_correct_rejected(self):
        suite = _suite()
        results = [_result_for(c, action=c.acceptable[0], correct=True) for c in suite.cases]
        results[0] = _result_for(suite.cases[0], outcome="unknown", action="unknown", correct=True)
        with self.assertRaises(RecordError):
            evaluate(_record_for(suite, results), suite, suite_path=str(SUITE_PATH))

    def test_error_without_kind_rejected(self):
        suite = _suite()
        results = [_result_for(c, action=c.acceptable[0], correct=True) for c in suite.cases]
        results[0] = _result_for(suite.cases[0], outcome="error", action=None, correct=None)
        with self.assertRaises(RecordError):
            evaluate(_record_for(suite, results), suite, suite_path=str(SUITE_PATH))

    def test_error_marked_correct_rejected(self):
        suite = _suite()
        results = [_result_for(c, action=c.acceptable[0], correct=True) for c in suite.cases]
        results[0] = _result_for(suite.cases[0], outcome="error", action=None,
                                 correct=True, error_kind="transport")
        with self.assertRaises(RecordError):
            evaluate(_record_for(suite, results), suite, suite_path=str(SUITE_PATH))

    def test_refusal_with_action_rejected(self):
        suite = _suite()
        results = [_result_for(c, action=c.acceptable[0], correct=True) for c in suite.cases]
        results[0] = _result_for(suite.cases[0], outcome="refusal", action="inspect_source",
                                 correct=None)
        with self.assertRaises(RecordError):
            evaluate(_record_for(suite, results), suite, suite_path=str(SUITE_PATH))

    def test_probability_sum_not_one_rejected(self):
        suite = _suite()
        c = suite.cases[0]
        r = _result_for(c, action=c.acceptable[0], correct=True)
        r.probabilities = {o: 0.1 for o in _dist(c.acceptable[0])}
        results = [r] + [_result_for(x, action=x.acceptable[0], correct=True)
                         for x in suite.cases[1:]]
        with self.assertRaises(RecordError):
            evaluate(_record_for(suite, results), suite, suite_path=str(SUITE_PATH))

    def test_nonfinite_probability_rejected(self):
        suite = _suite()
        c = suite.cases[0]
        r = _result_for(c, action=c.acceptable[0], correct=True)
        d = _dist(c.acceptable[0])
        d[c.acceptable[0]] = float("inf")
        r.probabilities = d
        results = [r] + [_result_for(x, action=x.acceptable[0], correct=True)
                         for x in suite.cases[1:]]
        with self.assertRaises(RecordError):
            evaluate(_record_for(suite, results), suite, suite_path=str(SUITE_PATH))

    def test_action_not_argmax_rejected(self):
        suite = _suite()
        c = suite.cases[0]
        other = next(o for o in _dist(c.acceptable[0]) if o != c.acceptable[0])
        r = _result_for(c, action=c.acceptable[0], correct=True)
        r.probabilities = _dist(other, 0.9)  # argmax is `other`, not the action
        results = [r] + [_result_for(x, action=x.acceptable[0], correct=True)
                         for x in suite.cases[1:]]
        with self.assertRaises(RecordError):
            evaluate(_record_for(suite, results), suite, suite_path=str(SUITE_PATH))

    def test_confidence_must_be_finite(self):
        suite = _suite()
        c = suite.cases[0]
        r = _result_for(c, action=c.acceptable[0], correct=True)
        r.confidence = float("nan")
        results = [r] + [_result_for(x, action=x.acceptable[0], correct=True)
                         for x in suite.cases[1:]]
        with self.assertRaises(RecordError):
            evaluate(_record_for(suite, results), suite, suite_path=str(SUITE_PATH))


class TestRetainedRequestBinding(unittest.TestCase):
    """A live record retains the exact prompt; replay binds it to the case."""

    def _live_like(self):
        from decision_lab.routes import build_request, get_route
        suite = _suite()
        results = []
        for c in suite.cases:
            action = c.acceptable[0]
            results.append(
                CaseResult(
                    case_id=c.id, source_group=c.source_group, split=c.split,
                    digest=case_digest(c), outcome="ok", action=action,
                    probabilities=_dist(action), model="jev-1.13.0", confidence=0.5,
                    http_status=200,
                    endpoint=get_route("jev").endpoint, request=build_request("jev", c),
                    correct=True,
                    raw={"model": "jev-1.13.0", "answers": {"next_action": {
                        "type": "choice", "choice": action,
                        "probabilities": _dist(action), "confidence": 0.5,
                    }}},
                )
            )
        rec = Record(
            provenance="live", route="jev", native_model="jev-1.13.0",
            suite_path=str(SUITE_PATH), suite_digest=suite_digest(suite),
            protocol={}, results=results, synthetic=False,
        )
        return suite, rec

    def test_matching_retained_request_evaluates(self):
        suite, rec = self._live_like()
        rep = evaluate(rec, suite, suite_path=str(SUITE_PATH))
        self.assertEqual(rep.answered, len(suite.cases))

    def test_tampered_request_body_detected(self):
        suite, rec = self._live_like()
        rec.results[0].request = dict(rec.results[0].request)
        rec.results[0].request["model"] = "tampered"
        with self.assertRaises(RecordError) as ctx:
            evaluate(rec, suite, suite_path=str(SUITE_PATH))
        self.assertIn("request", str(ctx.exception).lower())

    def test_endpoint_mismatch_detected(self):
        suite, rec = self._live_like()
        rec.results[0].endpoint = "https://evil.invalid/v1/systemone"
        with self.assertRaises(RecordError):
            evaluate(rec, suite, suite_path=str(SUITE_PATH))

    def test_partial_retained_request_rejected(self):
        suite, rec = self._live_like()
        rec.results[0].request = None
        with self.assertRaises(RecordError):
            evaluate(rec, suite, suite_path=str(SUITE_PATH))

    def test_removing_the_whole_live_request_rejected(self):
        suite, rec = self._live_like()
        rec.results[0].request = None
        rec.results[0].endpoint = None
        with self.assertRaises(RecordError):
            evaluate(rec, suite)

    def test_raw_response_disagreement_rejected(self):
        suite, rec = self._live_like()
        rec.results[0].raw['answers']['next_action']['choice'] = 'unknown'
        with self.assertRaises(RecordError):
            evaluate(rec, suite)

    def test_retained_request_survives_write_read_roundtrip(self):
        suite, rec = self._live_like()
        with tempfile.TemporaryDirectory() as d:
            out = write_record(Path(d) / "run", rec)
            loaded = load_record(out)
        self.assertEqual(loaded.results[0].endpoint, rec.results[0].endpoint)
        self.assertEqual(loaded.results[0].request, rec.results[0].request)
        evaluate(loaded, suite, suite_path=str(SUITE_PATH))

    def test_native_confidence_survives_roundtrip(self):
        suite, rec = self._live_like()
        rec.results[0].confidence = 0.123
        with tempfile.TemporaryDirectory() as d:
            out = write_record(Path(d) / "run", rec)
            loaded = load_record(out)
        self.assertEqual(loaded.results[0].confidence, 0.123)


if __name__ == "__main__":
    unittest.main()
