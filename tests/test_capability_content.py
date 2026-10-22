"""Dated capability provenance and reader/query consistency, without network."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


class CapabilityContentTests(unittest.TestCase):
    def test_cards_resolve_sources_and_reader_sections(self):
        index = read("catalog/index.json")
        book = read(index["capabilities"])
        registry = read(book["source_registry"])
        sources = {source["id"] for source in registry["sources"]}
        guide = (ROOT / book["reader"]).read_text(encoding="utf-8")
        ids = [card["id"] for card in book["capabilities"]]
        self.assertEqual(len(ids), 7)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(book["checked_at"], registry["checked_at"])
        for card in book["capabilities"]:
            with self.subTest(card=card["id"]):
                self.assertTrue(card["source_ids"])
                self.assertTrue(set(card["source_ids"]) <= sources)
                self.assertIn("## " + card["id"] + "\n", guide)
                self.assertTrue(card["hypothesis"])
                self.assertTrue(card["controls"])
                self.assertTrue(card["metrics"])
                self.assertEqual(card["provider_status"], "NOT_RUN")
                self.assertEqual(card["provider_results"], [])
                self.assertTrue((ROOT / card["lab"]["reader"].split("#")[0]).is_file())

    def test_capability_query_uses_its_own_date_and_complete_record(self):
        book = read("catalog/capabilities.json")
        expected = [card for card in book["capabilities"]
                    if "criteria" in json.dumps(card, ensure_ascii=False).casefold()]
        result = subprocess.run(
            [sys.executable, "tools/catalog.py", "capabilities", "--query", "criteria", "--json"],
            cwd=ROOT, text=True, capture_output=True, check=True,
        )
        output = json.loads(result.stdout)
        self.assertTrue(expected)
        self.assertEqual(output["as_of"], book["checked_at"])
        self.assertEqual(output["records"], expected)
        self.assertEqual(output["count"], len(expected))

    def test_current_probe_design_preserves_original_fixture_provenance(self):
        current = read("research/2026-10-22/public_probe_protocol.json")
        old = read(current["derived_from"])
        self.assertEqual(current["fixtures"], old["fixtures"])
        self.assertEqual(current["questions"], old["questions"])
        self.assertEqual([item["id"] for item in current["checks"]],
                         [item["id"] for item in old["checks"]])
        source_ids = {source["id"] for source in read("research/2026-10-22/updates.json")["sources"]}
        self.assertEqual(current["status"], "NOT_RUN")
        self.assertFalse(current["execution_included"])
        self.assertEqual(current["run_log"], [])
        for check in current["checks"]:
            self.assertEqual(check["status"], "NOT_RUN")
            self.assertTrue(set(check["current_source_ids"]) <= source_ids)
        image_probe = next(item for item in current["checks"] if item["id"] == "P12_INLINE_IMAGES")
        self.assertIn("320x320", image_probe["asset_specification"])
        self.assertIn("assets", image_probe["expected"]["typesafe_native"])
        self.assertNotIn("Text-only model", image_probe["expected"]["typesafe_native"])


if __name__ == "__main__":
    unittest.main()
