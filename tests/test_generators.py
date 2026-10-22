"""Exact oracles, transformation invariants, and family isolation."""
import copy
import json
import unittest
from fractions import Fraction
from decision_lab import generators as g


class GeneratorTests(unittest.TestCase):
    def test_seed_serialization_splits_and_reproducibility(self):
        for kind in g.KINDS:
            data = g.generate_dataset(kind, seed=41, units=40)
            self.assertEqual(data, json.loads(json.dumps(g.generate_dataset(kind, seed=41, units=40))))
            self.assertEqual(g.validate_dataset(data)["families"], 40)
            small = g.generate_dataset(kind, seed=41, units=20)
            self.assertEqual(data["rows"][:len(small["rows"])], small["rows"])
            self.assertEqual({r["split"] for r in data["rows"]}, {"train", "dev", "calibration", "test"})
            self.assertTrue(all("oracle" not in g.provider_request(r) for r in data["rows"]))

    def test_probability_exact_expected_loss(self):
        result = g.probability_oracle({"weights": [1, 2], "loss_matrix": {"a": [0, 3], "b": [3, 0]}})
        self.assertEqual(result["probabilities"], ["1/3", "2/3"])
        self.assertEqual(result["expected_loss"], {"a": "2", "b": "1"})
        self.assertEqual(result["best_actions"], ["b"])
        for row in g.generate_dataset("probability")["rows"]:
            self.assertEqual(sum(map(Fraction, row["oracle"]["probabilities"])), 1)

    def test_document_schema_insufficiency(self):
        rows = g.generate_dataset("documents", units=1)["rows"]
        base, reorder, twin = rows
        self.assertEqual(base["oracle"], reorder["oracle"])
        self.assertEqual(base["oracle"]["minimal_evidence"], ["v2"])
        self.assertEqual(base["oracle"]["gold_fields"], twin["oracle"]["gold_fields"])
        self.assertFalse(set(base["oracle"]["best_actions"]) & set(twin["oracle"]["best_actions"]))

    def test_rules_and_minimal_counterexample(self):
        data = g.generate_dataset("rules", units=2)
        self.assertEqual({r["latent_world"]["variables"] for r in data["rows"]}, {2, 3})
        for row in data["rows"]:
            world = row["latent_world"]
            errors = sorted(s for s in world["truth_table"] if world["truth_table"][s] != world["candidate_table"][s])
            self.assertEqual(row["oracle"]["counterexample"], errors[0])
            self.assertNotIn("truth_table", row["request"]["input"])

    def test_geometry_all_relations_and_transforms(self):
        data = g.generate_dataset("geometry", units=3)
        self.assertEqual({r["oracle"]["relation"] for r in data["rows"]}, {"contains", "touching", "disjoint"})
        self.assertEqual({r["condition"] for r in data["rows"]}, {"base", "translation", "scale", "color"})
        self.assertRaises(ValueError, g.geometry_relation, [0, 0, 2, 2], [1, 1, 3, 3])

    def test_projection_rejects_injected_editorial_truth_and_bad_metadata(self):
        data = g.generate_dataset("rules", units=1)
        data["rows"][0]["request"]["oracle"] = data["rows"][0]["oracle"]
        self.assertRaises(ValueError, g.provider_request, data["rows"][0])
        self.assertRaises(ValueError, g.validate_dataset, data)
        data = g.generate_dataset("documents", units=1)
        data["rows"][0]["latent_world"]["documents"][0]["version"] = 2
        self.assertRaises(ValueError, g.validate_dataset, data)
        for value in (None, {}, {"schema_version": "generated/v1", "kind": "rules"}):
            self.assertRaises(ValueError, g.validate_dataset, value)

    def test_invalid_and_tampered(self):
        for args in (("bad", 0, 2), ("rules", True, 2), ("rules", 0, 0), ("rules", 0, 1.5)):
            self.assertRaises(ValueError, g.generate_dataset, *args)
        for mutation in (lambda d: d["rows"][1].update(split="test"),
                         lambda d: d["rows"][0]["oracle"].update(counterexample=None),
                         lambda d: d["rows"][0]["transformation"].update(expected_relation="guess")):
            data = g.generate_dataset("rules", units=1)
            mutation(data)
            self.assertRaises(ValueError, g.validate_dataset, data)


if __name__ == "__main__":
    unittest.main()
