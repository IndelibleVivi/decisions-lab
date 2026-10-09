"""Evidence/index consistency and public source boundary checks (no network)."""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('catalog_tool', ROOT/'tools/catalog.py')
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)

class ContentTests(unittest.TestCase):
    def test_group_index_covers_each_project_once(self):
        index,data=catalog.load()
        ids=[p for group in index['groups'] for p in group['projects']]
        source=[p['id'] for p in data['repositories']['repositories']]
        self.assertEqual(len(ids),len(set(ids)))
        self.assertEqual(set(ids),set(source))

    def test_generated_project_map_is_current(self):
        self.assertEqual(catalog.project_markdown(),(ROOT/'docs/projects.md').read_text(encoding='utf-8'))

    def test_snapshot_counts_and_no_raw_predictions(self):
        _,data=catalog.load()
        metadata=json.loads((ROOT/'research/2026-10-08/metadata.json').read_text())
        self.assertEqual(metadata['research_entities'],len(data['census']['entities']))
        self.assertEqual(metadata['repository_index_entries'],len(data['repositories']['repositories']))
        self.assertEqual(metadata['source_urls'],len(data['source_index']['sources']))
        self.assertEqual(metadata['live_inference_calls'],0)
        self.assertFalse((ROOT/'research/2026-10-08/reanalysis/sys1_order_inputs.jsonl').exists())

    def test_citations_resolved_and_narrative_coverage(self):
        text=(ROOT/'research/2026-10-08/report.md').read_text()
        self.assertNotIn('](#src-',text)
        self.assertNotIn('](#source-',text)
        for number in range(1, 10):
            self.assertIn(f'## {number:02d} · ', text)

if __name__ == '__main__': unittest.main()
