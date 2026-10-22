"""Counterexample repairs and controls are local algorithm evidence only."""
import copy
import json
import unittest
from decision_lab.generators import generate_dataset
from decision_lab import rule_workflow as w


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.dataset = generate_dataset("rules", seed=17, units=2)

    def test_exact_and_replay(self):
        record = w.run_rule_workflow(self.dataset, compiler="exact")
        self.assertEqual(record["summary"]["fully_correct"], 2)
        self.assertEqual(record["summary"]["proposal_count"], 2)
        self.assertTrue(w.replay_workflow(json.loads(json.dumps(record)))["valid"])
        self.assertFalse(record["model_utility_evidence"])
        for trace in record["traces"]:
            self.assertTrue(trace["rule_update"]["stale_verification"]["stale_program"])
            self.assertFalse(trace["rule_update"]["stale_verification"]["function_correct"])
            self.assertTrue(trace["rule_update"]["fresh_verification"]["function_correct"])
            self.assertIsNone(trace["overhead"]["cost"])
            self.assertEqual(trace["overhead"]["provider_calls"], 0)

    def test_repairs_and_repeated_original_control(self):
        repaired = w.run_rule_workflow(self.dataset)
        repeated = w.run_rule_workflow(self.dataset, control="repeated-original", max_rounds=2)
        self.assertEqual(repaired["summary"]["fully_correct"], 2)
        self.assertEqual(repeated["summary"]["fully_correct"], 0)
        for trace in repaired["traces"]:
            self.assertEqual(trace["repair_rounds"], 2)
            initial = trace["rounds"][0]["verification"]
            nstates = len(initial["checked_states"])
            self.assertEqual(initial["hamming_distance"], 2)
            self.assertEqual(initial["hamming_rate"], 2 / nstates)
            self.assertEqual(initial["weighted_loss"], 2 / (nstates + 4))
            self.assertEqual(trace["rounds"][0]["verification"]["minimal_counterexample"], min(trace["rounds"][0]["proposal"]["truth_table"]))
            self.assertEqual(trace["overhead"]["proposal_count_per_use"], 3 / 100)

    def test_memorized_bad_repair_rejected_on_unseen_states(self):
        record = w.run_rule_workflow(self.dataset, compiler="memorize", max_rounds=1)
        for trace in record["traces"]:
            self.assertFalse(trace["final"]["function_correct"])
            self.assertGreater(trace["final"]["held_out_hamming_distance"], 0)
            first = trace["rounds"][0]["feedback_emitted"]
            self.assertEqual(trace["rounds"][1]["proposal"]["truth_table"][first["state"]], first["expected"])

    def test_random_control_reproducible_and_feedback_provenance(self):
        a = w.run_rule_workflow(self.dataset, control="random-feedback", seed=42)
        self.assertEqual(a, w.run_rule_workflow(self.dataset, control="random-feedback", seed=42))
        self.assertEqual(a["traces"][0]["rounds"][0]["feedback_emitted"]["kind"], "random-state")

    def test_imported_bad_repair_and_version(self):
        proposals = {}
        for row in self.dataset["rows"]:
            if row["condition"] != "base":
                continue
            world = row["latent_world"]
            table = {s: not value for s, value in world["truth_table"].items()}
            first = {"rule_version": 1, "truth_table": table}
            second = copy.deepcopy(first)
            state = min(table)
            second["truth_table"][state] = world["truth_table"][state]
            proposals[row["unit_id"]] = [first, second]
        record = w.run_rule_workflow(self.dataset, proposals=proposals)
        self.assertEqual(record["evidence"], "imported")
        self.assertEqual(record["summary"]["fully_correct"], 0)
        self.assertTrue(w.replay_workflow(record)["valid"])
        bad = copy.deepcopy(proposals)
        del next(iter(bad.values()))[0]["truth_table"]["00"]
        self.assertRaises(ValueError, w.run_rule_workflow, self.dataset, proposals=bad)
        world = self.dataset["rows"][0]["latent_world"]
        stale = {"rule_version": 0, "truth_table": world["truth_table"]}
        result = w.verify_program(world, stale)
        self.assertEqual(result["hamming_distance"], 0)
        self.assertFalse(result["function_correct"])

    def test_exact_solver_and_held_out_excludes_feedback(self):
        self.assertEqual(w.solve_rule({"variables": 2, "rule": "Trigger exactly on states 01,11"}),
                         {"00": False, "01": True, "10": False, "11": True})
        self.assertRaises(ValueError, w.solve_rule, {"variables": 2, "rule": "Trigger exactly on states 99"})
        record = w.run_rule_workflow(self.dataset)
        for trace in record["traces"]:
            for item in trace["rounds"]:
                seen = {f["state"] for f in item["feedback_received"]}
                held_out = set(item["verification"]["held_out_states"])
                self.assertFalse(seen & held_out)
                self.assertEqual(seen | held_out, set(item["proposal"]["truth_table"]))

    def test_validation_rejects_bad_options_and_tampered_trace(self):
        for kwargs in ({"uses": 0}, {"max_rounds": -1}, {"compiler": "model"}, {"control": "guess"}):
            self.assertRaises(ValueError, w.run_rule_workflow, self.dataset, **kwargs)
        record = w.run_rule_workflow(self.dataset)
        record["traces"][0]["rounds"][0]["proposal"]["truth_table"]["00"] ^= True
        self.assertRaises(ValueError, w.replay_workflow, record)
        self.assertRaises(ValueError, w.run_rule_workflow, generate_dataset("geometry"))


if __name__ == "__main__":
    unittest.main()
