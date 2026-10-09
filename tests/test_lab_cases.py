"""Schema / suite validation tests: the guards that reject bad case data."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from decision_lab.cases import CaseError, load_suite, parse_case, validate_suite, Suite


def _write(tmp: Path, name: str, data) -> Path:
    p = tmp / name
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def _case(**over) -> dict:
    base = {
        "id": "c1",
        "source_group": "g1",
        "split": "dev",
        "task": {"document": "some doc text", "claim": "claim", "source_ref": ""},
        "acceptable": ["inspect_source"],
        "rationale": "because",
    }
    base.update(over)
    return base


class TestSchema(unittest.TestCase):
    def test_minimal_valid_case(self):
        c = parse_case(_case())
        self.assertEqual(c.id, "c1")
        self.assertEqual(c.acceptable, ["inspect_source"])

    def test_missing_required_field(self):
        raw = _case()
        del raw["rationale"]
        with self.assertRaises(CaseError):
            parse_case(raw)

    def test_bad_split_value(self):
        with self.assertRaises(CaseError):
            parse_case(_case(split="train"))

    def test_bad_action_value(self):
        with self.assertRaises(CaseError):
            parse_case(_case(acceptable=["inspect_source", "do_something_else"]))

    def test_empty_acceptable_rejected(self):
        with self.assertRaises(CaseError):
            parse_case(_case(acceptable=[]))

    def test_duplicate_acceptable_rejected(self):
        with self.assertRaises(CaseError):
            parse_case(_case(acceptable=["inspect_source", "inspect_source"]))

    def test_empty_rationale_rejected(self):
        with self.assertRaises(CaseError):
            parse_case(_case(rationale="  "))

    def test_vacuous_task_rejected(self):
        with self.assertRaises(CaseError):
            parse_case(
                _case(task={"document": "", "claim": "", "question": "  ", "source_ref": ""})
            )


class TestSuite(unittest.TestCase):
    def test_duplicate_ids_rejected(self):
        s = Suite()
        s.cases.append(parse_case(_case(id="dup")))
        s.cases.append(parse_case(_case(id="dup")))
        with self.assertRaises(CaseError) as ctx:
            validate_suite(s)
        self.assertIn("duplicate", str(ctx.exception))

    def test_source_group_split_leak_rejected(self):
        s = Suite()
        s.cases.append(parse_case(_case(id="a", source_group="g", split="dev")))
        s.cases.append(parse_case(_case(id="b", source_group="g", split="test")))
        with self.assertRaises(CaseError) as ctx:
            validate_suite(s)
        self.assertIn("spans multiple splits", str(ctx.exception))

    def test_empty_suite_rejected(self):
        with self.assertRaises(CaseError):
            validate_suite(Suite())

    def test_load_missing_file(self):
        with self.assertRaises(CaseError):
            load_suite("/nonexistent/nope.json")

    def test_load_invalid_json(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.json"
            p.write_text("{ not json", encoding="utf-8")
            with self.assertRaises(CaseError):
                load_suite(p)


class TestRealSuite(unittest.TestCase):
    SUITE = Path(__file__).resolve().parent.parent / "experiments" / "next-action" / "cases.json"

    def test_real_suite_is_usable_and_split(self):
        suite = load_suite(self.SUITE)
        self.assertGreaterEqual(len(suite.cases), 20)
        self.assertTrue(suite.split("dev"))
        self.assertTrue(suite.split("test"))
        # every language variant group stays within one split (validated on load)
        groups = {c.source_group for c in suite.cases}
        self.assertGreaterEqual(len(groups), 8)

    def test_real_suite_ids_unique(self):
        suite = load_suite(self.SUITE)
        ids = [c.id for c in suite.cases]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
