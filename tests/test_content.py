"""Evidence/index consistency and public source boundary checks (no network)."""
import importlib.util
import json
import subprocess
import sys
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

    def test_increment_preserves_snapshot_and_resolves_sources(self):
        index, _ = catalog.load()
        update = json.loads((ROOT/index['latest_update']['path']).read_text())
        self.assertEqual(update['baseline'], index['source_root'])
        self.assertEqual(update['checked_at'], index['latest_update']['date'])
        self.assertLess(index['snapshot'], update['checked_at'])
        sources = {source['id'] for source in update['sources']}
        self.assertEqual(len(sources), len(update['sources']))
        changes = [change['id'] for change in update['changes']]
        self.assertEqual(len(changes), len(set(changes)))
        for change in update['changes']:
            self.assertTrue(change['source_ids'])
            self.assertTrue(set(change['source_ids']) <= sources, change['id'])
        for item in update['not_rechecked']:
            if 'source_id' in item:
                self.assertIn(item['source_id'], sources)

    def test_new_catalog_queries_return_their_own_dates(self):
        index, _ = catalog.load()
        for kind, query, source_path, date_key, records_key in (
            ('updates', 'jev', index['latest_update']['path'], 'checked_at', 'changes'),
            ('recipes', 'NPC', index['recipes'], 'updated_at', 'recipes'),
        ):
            source = json.loads((ROOT/source_path).read_text())
            result = subprocess.run([sys.executable, str(ROOT/'tools/catalog.py'), kind,
                                     '--query', query, '--json'], check=True, capture_output=True, text=True)
            output = json.loads(result.stdout)
            expected = [r for r in source[records_key]
                        if query.casefold() in json.dumps(r, ensure_ascii=False).casefold()]
            self.assertTrue(expected)
            self.assertEqual(output['as_of'], source[date_key])
            self.assertEqual(output['records'], expected)
            self.assertEqual(output['count'], len(expected))

if __name__ == '__main__': unittest.main()
