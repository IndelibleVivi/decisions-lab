"""Independent finite-world boundaries and retained native replay; no network."""
import copy
import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest

from decision_lab import api_lab as al, collection, role_tasks as roles
from decision_lab.cli import main


class RoleTasksTests(unittest.TestCase):
    def setUp(self):
        self.suite = roles.build_suite()

    def case(self, family, number, condition="baseline"):
        return next(r for r in self.suite.rows if r["id"] == f"role-{family}-{number:02d}-{condition}")

    def actions(self, family, number):
        row = self.case(family, number)
        return [row["rubric"]["mapping"][v] for v in row["rubric"]["questions"]["next"]["acceptable"]]

    def test_independent_expected_boundaries(self):
        # New correction contradicts old keyword lure: none is a normal answer.
        self.assertEqual(self.actions("evidence", 1), [{"kind": "none"}])
        self.assertEqual(self.actions("evidence", 2), [{"kind": "select", "items": ["b"]}])
        self.assertEqual(self.actions("evidence", 3), [
            {"kind": "select", "items": ["a"]}, {"kind": "select", "items": ["b"]}])
        self.assertEqual(self.actions("evidence", 4), [{"kind": "none"}])
        # Budget 5 exactly fits v2+permit; cheaper v1 cannot substitute.
        self.assertEqual(self.actions("context", 1), [{"kind": "pack", "items": ["b", "c"]}])
        self.assertEqual(self.actions("context", 2), [{"kind": "none"}])
        self.assertEqual(self.actions("context", 3), [
            {"kind": "pack", "items": ["a"]}, {"kind": "pack", "items": ["a", "b"]}])
        self.assertEqual(self.actions("context", 4), [{"kind": "none"}])
        self.assertEqual(self.actions("workflow", 1), [{"kind": "refresh"}])
        self.assertEqual(self.actions("workflow", 2), [{"kind": "review", "dependency": "draft"}])
        self.assertEqual(self.actions("workflow", 3), [{"kind": "work", "dependency": "audit"}])
        self.assertEqual(self.actions("workflow", 4), [{"kind": "advance"}])
        self.assertEqual([self.actions("control", i) for i in range(1, 5)], [
            [{"kind": "inspect"}], [{"kind": "handoff"}], [{"kind": "execute"}], [{"kind": "none"}]])

    def test_cardinality_variants_splits_and_seed(self):
        self.assertEqual(len(self.suite.rows), 48)
        self.assertEqual(self.suite.rows, roles.build_suite().rows)
        self.assertNotEqual(self.suite.rows, roles.build_suite(seed=1).rows)
        for family in roles.FAMILIES:
            for number in range(1, 5):
                base, reverse, opaque = [self.case(family, number, c) for c in roles.CONDITIONS]
                self.assertEqual(reverse["questions"][0]["choices"], list(reversed(base["questions"][0]["choices"])))
                self.assertEqual([c["description"] for c in base["questions"][0]["choices"]],
                                 [c["description"] for c in opaque["questions"][0]["choices"]])
                def canonical(row, field):
                    return sorted(json.dumps(row["rubric"]["mapping"][v], sort_keys=True)
                                  for v in row["rubric"][field] if v in row["rubric"]["mapping"])
                for row in (reverse, opaque):
                    self.assertEqual(canonical(row, "unsafe"), canonical(base, "unsafe"))
                    self.assertEqual(row["trial"]["unit_id"], base["trial"]["unit_id"])
                    self.assertEqual(row["trial"]["split"], base["trial"]["split"])
                    self.assertEqual({json.dumps(row["rubric"]["mapping"][v], sort_keys=True)
                                      for v in row["rubric"]["questions"]["next"]["acceptable"]},
                                     {json.dumps(base["rubric"]["mapping"][v], sort_keys=True)
                                      for v in base["rubric"]["questions"]["next"]["acceptable"]})
                self.assertFalse(set(base["rubric"]["mapping"]) & set(opaque["rubric"]["mapping"]))

    def test_all_native_routes_plan_and_no_oracle_leak(self):
        for route in al.ROUTES:
            manifest = roles.prepare(route, account_id="0" * 32 if route in al.CLOUDFLARE_ROUTES else None)
            self.assertEqual(al.validate_manifest(manifest)["requests"], 96)
            self.assertEqual(len(collection.validate_plan(collection.api_plan(manifest))), 96)
            body_text = json.dumps([r["body"] for r in manifest["requests"]])
            for hidden in ("acceptable", "unsafe", "loss_matrix", "world_provenance", "oracle", "rubric"):
                self.assertNotIn(hidden, body_text)
            entries = roles.baseline_entries(manifest)
            report = roles.evaluate(manifest, entries)
            self.assertEqual(report["summary"]["correct"], 96)
            self.assertEqual(report["summary"]["mean_workflow_loss"], 0)
            self.assertEqual(len(report["units"]), 16)
            self.assertTrue(all(p["both_correct"] == p["planned_pairs"] == 32 for p in report["pairs"]))
            # If all editorial metadata disappears, baseline output stays identical.
            stripped = copy.deepcopy(manifest)
            for request in stripped["requests"]:
                request.pop("rubric")
                request.pop("rubric_digest")
                request.pop("trial")
            self.assertEqual(roles.baseline_entries(stripped), entries)

    def test_text_and_necessary_hard_state_change_decisions(self):
        visible = json.loads(self.case("evidence", 2)["input"])
        previous = roles.policy_choices(visible)
        visible["state"]["documents"][1]["text"] = "更正旧版：纸舟采用灰边。"
        self.assertNotEqual(roles.policy_choices(visible), previous)
        visible = json.loads(self.case("context", 1)["input"])
        previous = roles.policy_choices(visible)
        visible["state"]["budget"] -= 1
        self.assertNotEqual(roles.policy_choices(visible), previous)
        visible = json.loads(self.case("workflow", 2)["input"])
        previous = roles.policy_choices(visible)
        visible["state"]["dependencies"]["draft"] = "accepted"
        self.assertNotEqual(roles.policy_choices(visible), previous)
        for family, number, field, value in (("control", 1, "effect", "absent"),
                                              ("control", 2, "controller", "agent"),
                                              ("control", 3, "permission", False)):
            visible = json.loads(self.case(family, number)["input"])
            previous = roles.policy_choices(visible)
            visible["state"][field] = value
            self.assertNotEqual(roles.policy_choices(visible), previous)

    def test_denominators_failure_unsafe_and_guards(self):
        manifest = roles.prepare("decisions", replicates=1)
        entries = roles.baseline_entries(manifest, "first")
        report = roles.evaluate(manifest, entries)
        self.assertLess(report["summary"]["correct"], 48)
        self.assertGreater(report["summary"]["illegal_suggestions"], 0)
        for row in report["requests"]:
            if row["unsafe"]:
                self.assertEqual(row["loss"], 1)
                self.assertFalse(row["correct"])
                self.assertTrue(row["guard_rejected"])
        self.assertLess(roles.evaluate(manifest, roles.baseline_entries(manifest, "abstain"))["summary"]["correct"], 48)
        entries = roles.baseline_entries(manifest)
        entries.pop()
        entries[0] = {"request_id": entries[0]["request_id"], "http_status": 500, "error": "synthetic failure"}
        summary = roles.evaluate(manifest, entries)["summary"]
        self.assertEqual((summary["planned"], summary["missing"], summary["valid"], summary["correct"]), (48, 1, 46, 46))
        self.assertEqual(summary["loss_sum"], 2)
        self.assertEqual(summary["accuracy_all_planned"], 46 / 48)
        self.assertEqual(summary["accuracy_conditional_valid"], 1)
        self.assertEqual(sum(f["planned"] for f in roles.evaluate(manifest, entries)["families"].values()), 48)
        empty = roles.evaluate(manifest, [])["summary"]
        self.assertEqual((empty["missing"], empty["loss_sum"], empty["valid"]), (48, 48, 0))
        self.assertIsNone(empty["accuracy_conditional_valid"])
        self.assertRaises(al.ApiLabError, roles.evaluate, manifest, entries + [entries[0]])

    def test_retained_loss_matrix_controls_replay(self):
        manifest = roles.prepare("decisions", replicates=1)
        def reseal(value):
            for request in value["requests"]:
                request["rubric_digest"] = al.digest(request["rubric"])
            value["manifest_digest"] = al.digest({k: v for k, v in value.items() if k != "manifest_digest"})
        for request in manifest["requests"]:
            request["rubric"]["loss_matrix"]["wrong_legal"] = .25
        reseal(manifest)
        report = roles.evaluate(manifest, roles.baseline_entries(manifest, "first"))
        row = next(r for r in report["requests"] if r["request_id"] == "role-evidence-01-baseline")
        self.assertEqual((row["correct"], row["unsafe"], row["loss"]), (False, False, .25))
        self.assertEqual(report["loss_matrix"]["wrong_legal"], .25)
        self.assertEqual(roles.evaluate(manifest, [])["loss_matrix"]["wrong_legal"], .25)
        for mutation in (lambda m: m.pop("correct"), lambda m: m.update(extra=0),
                         lambda m: m.update(wrong_legal=True), lambda m: m.update(wrong_legal=-.1),
                         lambda m: m.update(wrong_legal=1.1), lambda m: m.update(wrong_legal=".25")):
            changed = copy.deepcopy(manifest)
            mutation(changed["requests"][0]["rubric"]["loss_matrix"])
            reseal(changed)
            self.assertRaises(al.ApiLabError, roles.evaluate, changed, [])
        changed = copy.deepcopy(manifest)
        changed["requests"][0]["rubric"]["loss_matrix"]["wrong_legal"] = .5
        reseal(changed)
        self.assertRaisesRegex(al.ApiLabError, "matrices differ", roles.evaluate, changed, [])
        self.assertFalse(al.finite(float("inf")))
        self.assertFalse(al.finite(float("nan")))

    def test_context_guard_requires_complete_current_pack(self):
        visible = json.loads(self.case("context", 1)["input"])
        def candidate(items):
            return next(c["id"] for c in visible["candidates"]
                        if c["action"] == {"kind": "pack", "items": items})
        # Exact budget 3+2=5 is legal and complete.
        self.assertFalse(roles.guard_rejects(visible, candidate(["b", "c"])))
        # Current route alone is cheap but lacks the mandatory permit.
        self.assertTrue(roles.guard_rejects(visible, candidate(["b"])))
        # Old route plus permit is cheaper, complete by topic, still forbidden.
        self.assertTrue(roles.guard_rejects(visible, candidate(["a", "c"])))
        # none remains a legal suggestion even though a usable pack exists.
        none = next(c["id"] for c in visible["candidates"] if c["action"]["kind"] == "none")
        self.assertFalse(roles.guard_rejects(visible, none))
        manifest = roles.prepare("decisions", replicates=1)
        entries = roles.baseline_entries(manifest, "first")
        report = roles.evaluate(manifest, entries)
        row = next(r for r in report["requests"] if r["request_id"] == "role-context-01-baseline")
        self.assertEqual((row["correct"], row["unsafe"], row["guard_rejected"], row["loss"]),
                         (False, True, True, 1))

    def test_normal_none_not_unknown_and_semantic_error_not_guard_success(self):
        manifest = roles.prepare("decisions", replicates=1)
        report = roles.evaluate(manifest, roles.baseline_entries(manifest))
        row = next(r for r in report["requests"] if r["request_id"] == "role-evidence-01-baseline")
        self.assertEqual((row["outcome"], row["semantic_action"]), ("ok", {"kind": "none"}))
        report = roles.evaluate(manifest, roles.baseline_entries(manifest, "first"))
        row = next(r for r in report["requests"] if r["request_id"] == "role-evidence-01-baseline")
        self.assertEqual((row["correct"], row["guard_rejected"], row["loss"]), (False, False, .5))

    def cli(self, args):
        out = StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(args), 0)
        return json.loads(out.getvalue())

    def test_real_cli_prepare_and_retained_empty_replay(self):
        manifest = self.cli(["research", "role-scenarios", "--route", "decisions"])
        self.assertEqual(len(manifest["requests"]), 96)
        snapshot = {"schema": collection.SCHEMA, "plan": collection.api_plan(manifest),
                    "order": [r["id"] for r in manifest["requests"]], "attempts": [],
                    "provenance": "synthetic", "synthetic": True}
        collection._seal(snapshot)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "collection.json"
            path.write_text(json.dumps(snapshot), encoding="utf-8")
            report = self.cli(["research", "role-report", str(path)])
        self.assertEqual((report["actual_attempts"], report["summary"]["missing"]), (0, 96))
        self.assertTrue(report["synthetic"])
        self.assertFalse(report["live_verified"])
        # Two retained attempts for one request: replay the last failure,
        # preserve all other planned missing slots and count both attempts.
        first = roles.baseline_entries(manifest)[0]
        snapshot["attempts"] = [
            {"request_id": first["request_id"], "attempt": 1, "state": "ok",
             "parsed": first["response"], "http_status": 200, "elapsed_ms": 0},
            {"request_id": first["request_id"], "attempt": 2, "state": "transport_error",
             "parsed": None, "http_status": None, "elapsed_ms": 0}]
        collection._seal(snapshot)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "collection.json"
            path.write_text(json.dumps(snapshot), encoding="utf-8")
            report = self.cli(["research", "role-report", str(path)])
        self.assertEqual(report["actual_attempts"], 2)
        self.assertEqual(report["summary"]["missing"], 95)
        self.assertEqual(report["summary"]["outcomes"]["error"], 1)
        self.assertEqual(report["summary"]["loss_sum"], 96)


if __name__ == "__main__":
    unittest.main()
