"""Statistical contract checks using known synthetic effects, never model calls."""
import unittest

from decision_lab.comparison import (
    ComparisonError, compare_runs, evaluate_threshold, freeze_analysis_plan,
    risk_coverage, select_threshold,
)


def trial(i=0, **updates):
    row = dict(request_id=f"r{i}", question_id="q", unit_id=f"u{i}",
               source_family=f"f{i}", condition="base", replicate=0,
               split="test", outcome="ok", correct=True, loss=None,
               confidence=.8, latency_ms=None, cost=None)
    row.update(updates)
    return row


def ledger(rows, run_id="left", **updates):
    return dict(schema="decisions-lab.run-ledger/1", trials=rows,
                metadata=dict(dataset_id="dataset-v1", run_id=run_id), **updates)


class ComparisonTests(unittest.TestCase):
    def test_source_provenance_survives_comparison_without_live_claim(self):
        left = ledger([trial()], provenance="synthetic", synthetic=True)
        right = ledger([trial()], "right", provenance="collector", synthetic=False)
        result = compare_runs(left, right)
        self.assertEqual(result["evidence"]["left"]["provenance"], "synthetic")
        self.assertTrue(result["evidence"]["left"]["synthetic"])
        self.assertEqual(result["evidence"]["right"]["provenance"], "collector")
        self.assertFalse(result["evidence"]["right"]["live_verified"])
        unknown = compare_runs(ledger([trial()], provenance="imported"), right)
        self.assertIsNone(unknown["evidence"]["left"]["synthetic"])

    def test_retained_task_failure_loss_cannot_be_silently_repriced(self):
        rows = [trial(0, loss=.5, retained_failure_loss=.75, metric="role_workflow_loss", unsafe=False, guard_rejected=False),
                trial(1, outcome="missing", correct=None, loss=.75, retained_failure_loss=.75, metric="role_workflow_loss")]
        with self.assertRaisesRegex(ComparisonError, "retained task loss"):
            compare_runs(ledger(rows), ledger(rows), failure_loss=1)
        result = compare_runs(ledger(rows), ledger(rows), failure_loss=.75)
        self.assertEqual(result["left"]["workflow_loss"], .625)
        self.assertEqual(result["estimate"]["delta"], 0)
        self.assertEqual(risk_coverage(rows[:1])[0]["loss"], .5)
        self.assertEqual(result["left"]["role_metrics"], {"planned": 2, "unsafe": 0, "guard_rejected": 0})
        self.assertFalse(result["trace"][0]["left_guard_rejected"])
        unsafe = trial(0, loss=1, retained_failure_loss=.75, metric="role_workflow_loss", unsafe=True, guard_rejected=True)
        unpaired = compare_runs(ledger([unsafe]), ledger([]), failure_loss=.75)
        self.assertEqual(unpaired["left"]["role_metrics"]["unsafe"], 1)
        self.assertEqual(unpaired["right"]["role_metrics"]["unsafe"], 0)
        self.assertIsNone(unpaired["trace"][0]["right_guard_rejected"])
        old_projection = dict(rows[0])
        old_projection.pop("metric")
        old_projection["loss"] = 1
        with self.assertRaisesRegex(ComparisonError, "regenerate old ledgers"):
            compare_runs(ledger(rows[:1]), ledger([old_projection]), failure_loss=.75)

    def test_malformed_trial_identity_and_nonanswer_label_rejected(self):
        for update in ({"replicate": True}, {"replicate": -1}, {"replicate": "1"},
                       {"unit_id": ""}, {"source_family": 3}, {"outcome": "error", "correct": True}):
            with self.subTest(update=update), self.assertRaises(ComparisonError):
                compare_runs(ledger([trial(**update)]), ledger([trial()]))

    def test_null_and_known_effect(self):
        a = ledger([trial(i) for i in range(10)])
        b = ledger([trial(i, correct=False) for i in range(10)], "right")
        null = compare_runs(a, a, bootstrap_samples=100)
        self.assertEqual(null["estimate"]["ci95"], [0, 0])
        effect = compare_runs(a, b, bootstrap_samples=100)
        self.assertEqual(effect["estimate"]["delta"], 1)
        self.assertEqual(effect["estimate"]["ci95"], [1, 1])
        self.assertEqual(effect["planned"], 10)

    def test_cluster_not_variants_and_order_independent(self):
        a = [trial(i, source_family=f"f{i // 3}") for i in range(24)]
        b = [dict(r, correct=bool(i % 2)) for i, r in enumerate(a)]
        # 20 extra variants of a single unit must not acquire 20 unit votes.
        a += [trial(0, question_id=f"q{k}", source_family="f0") for k in range(20)]
        b += [dict(r, correct=False) for r in a[-20:]]
        first = compare_runs(ledger(a), ledger(b), seed=17, bootstrap_samples=100)
        second = compare_runs(ledger(list(reversed(a))), ledger(list(reversed(b))), seed=17, bootstrap_samples=100)
        self.assertEqual(first, second)
        self.assertEqual(first["estimate"]["units"], 24)
        self.assertEqual(first["estimate"]["clusters"], 8)
        self.assertLess(first["estimate"]["delta"], .55)

    def test_few_clusters_descriptive_even_with_many_trials(self):
        rows = [trial(i, source_family=f"f{i % 2}") for i in range(100)]
        result = compare_runs(ledger(rows), ledger(rows))
        self.assertIsNone(result["estimate"]["ci95"])
        self.assertEqual(result["estimate"]["inference"], "descriptive-only")

    def test_missing_and_failures_keep_planned_denominator(self):
        a = [trial(0), trial(1), trial(2, outcome="error", correct=None)]
        b = [trial(0), trial(1, outcome="unknown", correct=None)]
        result = compare_runs(ledger(a), ledger(b), failure_loss=2)
        self.assertEqual(result["paired"], 2)
        self.assertEqual(result["left_only"], 1)
        self.assertEqual(result["planned"], 3)
        self.assertEqual(result["right"]["outcomes"]["missing"], 1)
        self.assertAlmostEqual(result["right"]["workflow_loss"], 4 / 3)
        self.assertEqual(result["right"]["conditional_accuracy"], 1)
        self.assertIsNone(result["trace"][-1]["right_request_id"])

    def test_all_failure_outcomes(self):
        rows = [trial(i, outcome=o, correct=None) for i, o in enumerate(["unknown", "refusal", "error", "missing"])]
        result = compare_runs(ledger(rows), ledger(rows))
        self.assertEqual(result["left"]["workflow_loss"], 1)
        self.assertIsNone(result["left"]["conditional_accuracy"])

    def test_invalid_mappings_duplicates_and_leakage(self):
        cases = [([trial(), trial()], [trial()]),
                 ([trial()], [trial(source_family="other")]),
                 ([trial(0), trial(1, source_family="f0", split="calibration")], [trial()]),
                 ([trial()], [trial(split="calibration")])]
        for a, b in cases:
            with self.subTest(a=a, b=b), self.assertRaises(ComparisonError):
                compare_runs(ledger(a), ledger(b))

    def test_request_usage_once_and_unknown(self):
        rows = [trial(0, request_id="shared", latency_ms=4, cost={"amount": .2, "currency": "USD"}),
                trial(1, request_id="shared", latency_ms=4, cost={"amount": .2, "currency": "USD"})]
        metrics = compare_runs(ledger(rows), ledger(rows))["left_request_metrics"]
        self.assertEqual(metrics["requests"], 1)
        self.assertEqual(metrics["cost_total"], .2)
        self.assertEqual(metrics["latency_ms_total"], 4)
        rows[0]["cost"] = rows[1]["cost"] = None
        self.assertIsNone(compare_runs(ledger(rows), ledger(rows))["left_request_metrics"]["cost_total"])

    def test_explicit_requests_take_precedence(self):
        rows = [trial(0, latency_ms=999, cost=99), trial(1, request_id="r0", cost=88)]
        run = ledger(rows, requests=[dict(request_id="r0", latency_ms=5, cost={"amount": .1, "currency": "USD"})])
        metrics = compare_runs(run, run)["left_request_metrics"]
        self.assertEqual(metrics["latency_ms_total"], 5)
        self.assertEqual(metrics["cost_total"], .1)

    def test_unlabelled_or_mixed_currency_not_added(self):
        for costs in [(1, 2), ({"amount": 1, "currency": "USD"}, {"amount": 2, "currency": "EUR"}),
                      ({"amount": 1, "currency": "USD"}, None)]:
            rows = [trial(i, cost=c) for i, c in enumerate(costs)]
            self.assertIsNone(compare_runs(ledger(rows), ledger(rows))["left_request_metrics"]["cost_total"])

    def test_filters_and_empty(self):
        rows = [trial(0, split="calibration"), trial(1)]
        result = compare_runs(ledger(rows), ledger(rows), split="test")
        self.assertEqual(result["planned"], 1)
        self.assertIsNone(compare_runs(ledger([]), ledger([]))["estimate"]["delta"])

    def test_loss_and_error_are_separate(self):
        run = ledger([trial(loss=.2, correct=None)])
        result = compare_runs(run, run)
        self.assertEqual(result["left"]["workflow_loss"], .2)
        self.assertIsNone(result["left"]["error_loss"])
        with self.assertRaises(ComparisonError):
            compare_runs(ledger([trial(correct=None)]), ledger([trial(correct=None)]))

    def test_plan_frozen_and_checked(self):
        plan = freeze_analysis_plan(dataset_id="dataset-v1", comparison=["left", "right"])
        a, b = ledger([trial()]), ledger([trial()], "right")
        self.assertEqual(compare_runs(a, b, plan=plan)["split"], "test")
        for change in ({"dataset_id": "other"}, {"comparison": ["right", "left"]},
                       {"threshold": .5, "threshold_selection_split": "test"}):
            with self.subTest(change=change), self.assertRaises(ComparisonError):
                compare_runs(a, b, plan={**plan, **change})
        with self.assertRaises(ComparisonError):
            compare_runs(a, b, failure_loss=2, plan=plan)

    def test_correlated_cluster_uncertainty(self):
        a = [trial(i, source_family=f"f{i // 3}") for i in range(24)]
        b = [dict(r, correct=i // 3 >= 4) for i, r in enumerate(a)]
        estimate = compare_runs(ledger(a), ledger(b), seed=3)["estimate"]
        self.assertEqual(estimate["delta"], .5)
        self.assertGreater(estimate["ci95"][1] - estimate["ci95"][0], .5)

    def test_frozen_threshold_applied_to_planned_denominator(self):
        plan = freeze_analysis_plan(dataset_id="dataset-v1", comparison=["left", "right"], threshold=.9)
        result = compare_runs(ledger([trial(confidence=.8)]), ledger([trial(confidence=.95)], "right"), plan=plan)
        self.assertEqual(result["estimate"]["delta"], -1)
        self.assertEqual(result["left"]["outcomes"]["unknown"], 1)
        self.assertEqual(result["trace"][0]["left_original_outcome"], "ok")

    def test_metric_plan(self):
        plan = freeze_analysis_plan(dataset_id="dataset-v1", comparison=["left", "right"], metric="error_loss")
        result = compare_runs(ledger([trial(loss=.8)]), ledger([trial(loss=.2, correct=False)], "right"), plan=plan)
        self.assertEqual(result["estimate"]["delta"], 1)
        self.assertAlmostEqual(result["right"]["workflow_loss"], .2)


class SelectiveTests(unittest.TestCase):
    def test_ties_and_all_planned_denominator(self):
        rows = [trial(0, confidence=.9), trial(1, confidence=.9, correct=False),
                trial(2, confidence=None), trial(3, outcome="unknown", confidence=0, correct=None),
                trial(4, outcome="missing", correct=None)]
        points = risk_coverage(rows)
        self.assertEqual(len(points), 1)
        self.assertEqual(points[0]["selected"], 2)
        self.assertEqual(points[0]["coverage"], .4)
        self.assertEqual(points[0]["risk"], .5)

    def test_calibration_only_and_test_only(self):
        cal = [trial(0, split="calibration", confidence=.9),
               trial(1, split="calibration", confidence=.5, correct=False)]
        selected = select_threshold(cal, target_risk=0)
        self.assertEqual(selected["threshold"], .9)
        evaluated = evaluate_threshold([trial(2, confidence=.95), trial(3, confidence=.8)], selected)
        self.assertEqual(evaluated["coverage"], .5)
        self.assertFalse(evaluated["risk_guarantee"])
        with self.assertRaises(ComparisonError):
            select_threshold([trial()])
        with self.assertRaises(ComparisonError):
            evaluate_threshold(cal, selected)
        with self.assertRaises(ComparisonError):
            evaluate_threshold([trial(0)], selected)
        with self.assertRaises(ComparisonError):
            evaluate_threshold([trial(2)], .9)

    def test_reject_all(self):
        selected = select_threshold([trial(0, split="calibration", correct=False)], target_risk=0)
        self.assertTrue(selected["reject_all"])
        result = evaluate_threshold([trial(1)], selected)
        self.assertEqual(result["coverage"], 0)
        self.assertIsNone(result["risk"])

    def test_risk_loss_separate(self):
        result = risk_coverage([trial(loss=.2, correct=True)])[0]
        self.assertEqual(result["risk"], 0)
        self.assertEqual(result["loss"], .2)


if __name__ == "__main__":
    unittest.main()
