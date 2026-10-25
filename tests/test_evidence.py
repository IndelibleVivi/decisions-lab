"""Behavioral controls for the finite active-evidence research core."""
import copy
import json
import math
import random
import unittest

from decision_lab import evidence as e


def scenario(sid):
    return next(s for s in e.build_suite()["scenarios"] if s["id"] == sid)


def brute_force(s, compatible=None, asked=()):
    """Independent small-tree enumeration: enumerate possible observed branches."""
    worlds = s["hypotheses"] if compatible is None else compatible
    mass = sum(h["prior"] for h in worlds)
    stop = [s["abstain_loss"]] + [sum(h["prior"] * d["losses"][h["id"]] for h in worlds) / mass
                                    for d in s["decisions"]]
    alternatives = list(stop)
    spent = sum(q["cost"] for q in s["queries"] if q["id"] in asked)
    for query in s["queries"]:
        if query["id"] in asked or len(asked) >= s["max_queries"] or spent + query["cost"] > s["budget"]:
            continue
        observations = {h["observations"][query["id"]] for h in worlds}
        future = 0
        for observation in observations:
            group = [h for h in worlds if h["observations"][query["id"]] == observation]
            future += sum(h["prior"] for h in group) / mass * brute_force(s, group, (*asked, query["id"]))
        alternatives.append(query["cost"] + future)
    return min(alternatives)


class EvidenceTests(unittest.TestCase):
    def test_suite_is_original_finite_and_seed_changes_presentation_only(self):
        suite, changed = e.build_suite(), e.build_suite(42)
        e.validate_suite(suite)
        self.assertGreaterEqual(len({s["source_family"] for s in suite["scenarios"]}), 6)
        for a, b in zip(suite["scenarios"], changed["scenarios"]):
            self.assertEqual(a["id"], b["id"])
            self.assertEqual(sorted(a["hypotheses"], key=lambda h: h["id"]), sorted(b["hypotheses"], key=lambda h: h["id"]))
        with self.assertRaises(ValueError):
            e.build_suite(True)

    def test_xor_complement_requires_two_queries(self):
        s = scenario("xor-complement")
        for world in s["hypotheses"]:
            start = e.initial_state(s, world["id"])
            myopic, optimal = e.oracle(s, start, "myopic"), e.oracle(s, start)
            self.assertEqual(myopic["action"], "abstain")
            self.assertEqual(myopic["expected_loss"], 3)
            self.assertAlmostEqual(myopic["action_values"]["query:left"], 4)
            self.assertAlmostEqual(optimal["expected_loss"], 2)
            self.assertTrue(optimal["action"].startswith("query:"))
            state = e.step(s, start, optimal["action"])
            self.assertAlmostEqual(e.oracle(s, state, "stop")["expected_loss"], 3)
            state = e.step(s, state, e.oracle(s, state)["action"])
            state = e.step(s, state, e.oracle(s, state)["action"])
            score = e.evaluate_episode(s, state)
            self.assertEqual((score["query_count"], score["terminal_loss"], score["total_loss"]), (2, 0, 2))
            self.assertEqual([r["stop_risk_after"] for r in score["query_risks"]], [3, 0])
            self.assertFalse(score["wrong_commit"])

    def test_optimal_matches_independent_tree_enumeration(self):
        rng = random.Random(740)
        for _ in range(18):
            s = scenario("xor-complement")
            raw = [rng.randint(1, 9) for _ in range(4)]
            for h, weight in zip(s["hypotheses"], raw):
                h["prior"] = weight / sum(raw)
                h["observations"] = {q["id"]: str(rng.randrange(2)) for q in s["queries"]}
            for d in s["decisions"]:
                d["losses"] = {h["id"]: rng.randint(0, 15) for h in s["hypotheses"]}
            s["budget"], s["max_queries"] = rng.randrange(3), rng.randrange(3)
            state = e.initial_state(s, s["hypotheses"][0]["id"])
            self.assertAlmostEqual(e.oracle(s, state)["expected_loss"], brute_force(s))
            for query in [a for a in e.available_actions(s, state) if a.startswith("query:")]:
                after = e.step(s, state, query)
                observed = after["history"][0]["observation"]
                compatible = [h for h in s["hypotheses"] if h["observations"][query[6:]] == observed]
                self.assertAlmostEqual(e.oracle(s, after)["expected_loss"], brute_force(s, compatible, (query[6:],)))

    def test_same_history_different_actual_world_same_visible_and_action(self):
        s = scenario("xor-complement")
        first, second = e.initial_state(s, "h0"), e.initial_state(s, "h1")
        self.assertEqual(e.visible_state(s, first), e.visible_state(s, second))
        self.assertNotIn("world_id", e.visible_state(s, first))
        for mode in e.POLICIES:
            self.assertEqual(e.oracle(s, first, mode), e.oracle(s, second, mode))
        first, second = e.step(s, first, "query:left"), e.step(s, second, "query:left")
        self.assertEqual(e.visible_state(s, first), e.visible_state(s, second))
        self.assertEqual(e.oracle(s, first), e.oracle(s, second))
        self.assertEqual(e.choose_action(s, e.visible_state(s, first)), e.oracle(s, first)["action"])

    def test_public_view_retains_hypotheses_not_unseen_actual_observation(self):
        s = scenario("key-evidence")
        view = e.visible_state(s, e.initial_state(s, "h0"))
        self.assertEqual(view["history"], [])
        self.assertEqual(view["posterior"], {h["id"]: .5 for h in s["hypotheses"]})
        self.assertEqual(len(view["hypotheses"]), 2)
        for key, value in (("world_id", "h0"), ("spent", 2), ("posterior", {"h0": 1.0}), ("remaining_budget", 0)):
            forged = copy.deepcopy(view)
            forged[key] = value
            with self.assertRaises(ValueError):
                e.choose_action(s, forged)

    def test_derived_state_is_not_trusted(self):
        s = scenario("key-evidence")
        state = e.initial_state(s, "h0")
        for key, value in (("spent", -1), ("terminal", {"kind": "abstain"}), ("scenario_id", "other")):
            forged = copy.deepcopy(state)
            forged[key] = value
            for operation in (e.visible_state, e.available_actions, e.oracle):
                with self.assertRaises(ValueError):
                    operation(s, forged)
            with self.assertRaises(ValueError):
                e.step(s, forged, "abstain")

    def test_illegal_duplicate_and_budget_queries_leave_input_unchanged(self):
        s = scenario("xor-complement")
        s["budget"] = 1
        state = e.initial_state(s, "h0")
        unchanged = copy.deepcopy(state)
        for action in ("query:bogus", "commit:bogus", "missing", None):
            with self.assertRaises(ValueError):
                e.step(s, state, action)
            self.assertEqual(state, unchanged)
        state = e.step(s, state, "query:left")
        for action in ("query:left", "query:right"):
            with self.assertRaises(ValueError):
                e.step(s, state, action)
        self.assertIn("abstain", e.available_actions(s, state))
        self.assertIn("commit:even", e.available_actions(s, state))
        terminal = e.step(s, state, "abstain")
        self.assertEqual(e.available_actions(s, terminal), [])
        with self.assertRaises(ValueError):
            e.step(s, terminal, "commit:even")
        with self.assertRaises(ValueError):
            e.finish_failure(s, terminal, "error")

    def test_max_queries_and_budget_do_not_prevent_terminal_commit(self):
        s = scenario("key-evidence")
        s["budget"], s["max_queries"] = 1, 1
        state = e.step(s, e.initial_state(s, "h0"), "query:register")
        self.assertFalse(any(a.startswith("query:") for a in e.available_actions(s, state)))
        state = e.step(s, state, "commit:route-a")
        self.assertEqual(e.evaluate_episode(s, state)["total_loss"], 1)

    def test_zero_cost_ties_prefer_stop(self):
        s = scenario("uninformative")
        s["queries"][0]["cost"] = 0
        state = e.initial_state(s, "h0")
        result = e.oracle(s, state)
        self.assertEqual(result["action"], "commit:usual")
        self.assertAlmostEqual(result["action_values"]["query:index"], result["expected_loss"])
        s["budget"] = 0
        self.assertIn("query:index", e.available_actions(s, state))
        s["max_queries"] = 0
        self.assertNotIn("query:index", e.available_actions(s, state))

    def test_query_cost_tie_with_abstain_stops(self):
        s = scenario("key-evidence")
        s["queries"][0]["cost"] = 3
        s["budget"] = 3
        self.assertEqual(e.oracle(s, e.initial_state(s, "h0"))["action"], "abstain")

    def test_nonuniform_prior_and_asymmetric_loss(self):
        s = scenario("asymmetric-prior")
        state = e.initial_state(s, "h0")
        stop = e.oracle(s, state, "stop")
        self.assertAlmostEqual(stop["action_values"]["commit:allow"], 5)
        self.assertAlmostEqual(stop["action_values"]["commit:hold"], 3.6)
        self.assertEqual(stop["action"], "commit:hold")
        self.assertEqual(e.oracle(s, state)["action"], "query:audit")
        self.assertAlmostEqual(e.oracle(s, state)["expected_loss"], 1)
        after = e.step(s, state, "query:audit")
        self.assertEqual(e.visible_state(s, after)["posterior"], {"h0": 1.0})

    def test_robust_actions_are_worldwise_intersection_not_bayes_argmin(self):
        s = scenario("uninformative")
        info = e.oracle(s, e.initial_state(s, "h0"))
        self.assertEqual(info["action"], "commit:usual")
        self.assertEqual(info["robust_actions"], [])
        s = scenario("robust-stop")
        info = e.oracle(s, e.initial_state(s, "h0"))
        self.assertEqual(info["robust_actions"], ["commit:safe"])
        self.assertEqual(info["action"], "commit:safe")
        s["abstain_loss"] = 0
        self.assertEqual(e.oracle(s, e.initial_state(s, "h0"))["robust_actions"], ["commit:safe"])

    def test_unavailable_and_stale_controls(self):
        s = scenario("unavailable")
        self.assertEqual(e.oracle(s, e.initial_state(s, "h0"))["action"], "abstain")
        self.assertEqual(len({h["observations"]["archive"] for h in s["hypotheses"]}), 1)
        s = scenario("stale-entity")
        self.assertEqual(e.oracle(s, e.initial_state(s, "h0"))["action"], "query:current")
        self.assertEqual(e.oracle(s, e.initial_state(s, "h0"), "checklist")["action"], "query:old")

    def test_business_abstain_is_distinct_from_all_failures(self):
        s = scenario("unavailable")
        state = e.initial_state(s, "h0")
        abstain = e.evaluate_episode(s, e.step(s, state, "abstain"))
        self.assertEqual(abstain["terminal_loss"], 3)
        self.assertTrue(abstain["abstained"])
        self.assertFalse(abstain["failed"])
        self.assertTrue(abstain["completed"])
        for status in e.FAILURES:
            failure = e.evaluate_episode(s, e.finish_failure(s, state, status))
            self.assertFalse(failure["abstained"])
            self.assertTrue(failure["failed"])
            self.assertEqual(failure["failure_status"], status)
            self.assertEqual(failure["terminal_loss"], s["failure_loss"])
            self.assertEqual(failure["missing"], status == "missing")
            self.assertEqual(failure["completed"], status != "missing")
        with self.assertRaises(ValueError):
            e.finish_failure(s, state, "abstain")
        with self.assertRaises(ValueError):
            e.evaluate_episode(s, state)

    def test_actual_and_incompatible_observation_rejected(self):
        s = scenario("key-evidence")
        wrong = [{"action": "query:register", "observation": "当前路线乙"}]
        with self.assertRaises(ValueError):
            e.state_from_history(s, "h0", wrong)
        with self.assertRaises(ValueError):
            e.visible_from_history(s, [{"action": "query:register", "observation": "不存在"}])
        s = scenario("xor-complement")
        for h in s["hypotheses"]:
            h["observations"]["right"] = h["observations"]["left"]
        with self.assertRaises(ValueError):
            e.visible_from_history(s, [{"action": "query:left", "observation": "0"},
                                       {"action": "query:right", "observation": "1"}])

    def test_validation_rejects_bad_designs(self):
        mutations = [lambda s: s.update(budget=-1), lambda s: s.update(max_queries=True),
                     lambda s: s.update(abstain_loss=float("nan")), lambda s: s.update(failure_loss=float("inf")),
                     lambda s: s["queries"][0].update(cost=.5), lambda s: s["hypotheses"][0].update(prior=0),
                     lambda s: s["hypotheses"][0].update(prior=.7), lambda s: s["hypotheses"][0].update(prior=10**1000), lambda s: s["hypotheses"][0].update(observations={}),
                     lambda s: s["decisions"][0].update(losses={}),
                     lambda s: s["decisions"][0]["losses"].update(h0=-1),
                     lambda s: s["decisions"][0].update(id="register"),
                     lambda s: s["queries"].append(copy.deepcopy(s["queries"][0]))]
        for mutate in mutations:
            s = scenario("key-evidence")
            mutate(s)
            with self.assertRaises(ValueError):
                e.validate_suite({"schema": e.SUITE_SCHEMA, "scenarios": [s]})
        for key, count in (("hypotheses", 17), ("queries", 9)):
            s = scenario("key-evidence")
            s[key] = [copy.deepcopy(s[key][0]) for _ in range(count)]
            with self.assertRaises(ValueError):
                e.validate_suite({"schema": e.SUITE_SCHEMA, "scenarios": [s]})

    def test_replay_preserves_complete_planned_denominator_and_repeats(self):
        suite = e.build_suite()
        record = e.run_suite(suite, replicates=3)
        expected = sum(len(s["hypotheses"]) for s in suite["scenarios"]) * 3
        self.assertEqual(len(record["planned"]), expected)
        report = e.replay(record)
        self.assertEqual(report["summary"]["planned"], expected)
        self.assertEqual(report["summary"]["coverage"], 1)
        self.assertEqual(report["summary"]["source_families"], len(suite["scenarios"]))
        del record["episodes"][0]
        report = e.replay(record)
        self.assertEqual(report["summary"]["planned"], expected)
        self.assertEqual(report["summary"]["completed"], expected - 1)
        self.assertEqual(report["summary"]["missing"], 1)
        self.assertEqual(report["summary"]["failed"], 1)
        self.assertAlmostEqual(report["summary"]["coverage"], (expected - 1) / expected)
        self.assertIsNone(report["summary"]["expected_regret"])
        self.assertEqual(sum(g["planned"] for g in report["families"].values()), expected)

    def test_replay_missing_partial_trajectory_preserves_spend(self):
        s = scenario("xor-complement")
        suite = {"schema": e.SUITE_SCHEMA, "scenarios": [s]}
        record = e.run_suite(suite)
        record["episodes"][0]["history"] = record["episodes"][0]["history"][:1]
        report = e.replay(record)
        row = report["episodes"][0]
        self.assertEqual((row["query_cost"], row["missing"], row["failed"]), (1, True, True))
        self.assertEqual(row["total_loss"], 1 + s["failure_loss"])

    def test_replay_rejects_identity_duplicates_and_bad_histories(self):
        record = e.run_suite(e.build_suite())
        mutations = [lambda r: r["episodes"].append(copy.deepcopy(r["episodes"][0])),
                     lambda r: r["episodes"][0].update(id="other"),
                     lambda r: r["planned"].pop(), lambda r: r.update(policy="stop"),
                     lambda r: r["episodes"][0]["history"].append({"action": "abstain"}),
                     lambda r: r["episodes"][0].update(state={"spent": 999})]
        for mutate in mutations:
            changed = copy.deepcopy(record)
            mutate(changed)
            with self.assertRaises(ValueError):
                e.replay(changed)
        # A duplicate before termination and a legal query above budget both fail.
        for budget, history in [(2, [{"action": "query:left", "observation": "0"}] * 2),
                                (1, [{"action": "query:left", "observation": "0"}, {"action": "query:right", "observation": "0"}])]:
            s = scenario("xor-complement")
            s["budget"] = budget
            record = e.run_suite({"schema": e.SUITE_SCHEMA, "scenarios": [s]})
            plan = next(p for p in record["planned"] if p["world_id"] == "h0")
            next(row for row in record["episodes"] if row["id"] == plan["id"])["history"] = history
            with self.assertRaises(ValueError):
                e.replay(record)

    def test_replay_rescores_valid_changed_history_and_ignores_cached_score(self):
        s = scenario("key-evidence")
        record = e.run_suite({"schema": e.SUITE_SCHEMA, "scenarios": [s]})
        record["episodes"][0].update(history=[{"action": "abstain"}], score={"total_loss": -900})
        record["summary"] = {"total_loss": -900}
        report = e.replay(record)
        self.assertEqual(report["episodes"][0]["total_loss"], 3)
        self.assertIsNone(report["episodes"][0]["expected_regret"])
        self.assertIsNone(report["summary"]["expected_regret"])
        # A changed valid suite is explicitly re-scored, not authenticated.
        record["suite"]["scenarios"][0]["abstain_loss"] = 7
        self.assertEqual(e.replay(record)["episodes"][0]["terminal_loss"], 7)

    def test_expected_regret_and_realized_loss_are_different_quantities(self):
        s = scenario("asymmetric-prior")
        report = e.replay(e.run_suite({"schema": e.SUITE_SCHEMA, "scenarios": [s]}, "stop"))
        realized = {row["world_id"]: row["total_loss"] for row in report["episodes"]}
        regrets = [row["expected_regret"] for row in report["episodes"]]
        self.assertEqual(realized, {"h0": 4, "h1": 0})
        self.assertTrue(all(math.isclose(v, 2.6) for v in regrets))
        self.assertAlmostEqual(report["summary"]["prior_weighted_mean_total_loss"], 3.6)
        self.assertAlmostEqual(report["summary"]["mean_total_loss"], 2)
        self.assertAlmostEqual(report["summary"]["policy_expected_loss"], 3.6)
        self.assertAlmostEqual(report["summary"]["expected_regret"], 2.6)

    def test_record_freezes_suite_and_has_no_live_claim(self):
        suite = e.build_suite()
        record = e.run_suite(suite)
        suite["scenarios"][0]["title"] = "changed later"
        self.assertNotEqual(record["suite"]["scenarios"][0]["title"], "changed later")
        self.assertTrue(record["synthetic"])
        self.assertEqual(record["provenance"], "synthetic")
        self.assertFalse(record["live_verified"])
        record["live_verified"] = True
        self.assertFalse(e.replay(record)["live_verified"])
        restored = json.loads(json.dumps(record, ensure_ascii=False, allow_nan=False))
        self.assertEqual(e.replay(restored)["summary"]["planned"], len(record["planned"]))

    def test_unknown_synthetic_provenance_remains_unknown_in_core_replay(self):
        record = e.run_suite(e.build_suite())
        record["synthetic"] = None
        self.assertIsNone(e.replay(record)["synthetic"])
        self.assertNotIn("independent_source_count", e.replay(record)["summary"])
        record["synthetic"] = "unknown"
        with self.assertRaisesRegex(ValueError, "synthetic marker"):
            e.replay(record)

    def test_external_trajectory_cannot_claim_unobserved_policy_expected_regret(self):
        record = e.run_suite(e.build_suite())
        record["policy"] = "external-model"
        record["planned"] = e.planned_episodes(record["suite"], "external-model", 1)
        report = e.replay(record)
        self.assertIsNone(report["summary"]["expected_regret"])
        self.assertTrue(all(row["expected_regret"] is None for row in report["episodes"]))
        self.assertTrue(all(row["total_loss"] >= 0 for row in report["episodes"]))


if __name__ == "__main__":
    unittest.main()
