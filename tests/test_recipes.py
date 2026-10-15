"""Integrity checks for the playbook index (catalog/recipes.json) and docs/playbook.md.

Offline only: no network, no provider calls. These tests reject an index that
invents a project URL, dates a recipe with a project this round did not
re-check, marks an unimplemented recipe as runnable, breaks the site fragment
anchor for a recipe, or contradicts the reader-facing Markdown.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SCHEMA = 'decisions-lab.recipes/1'
UPDATED_AT = '2026-10-15'              # page edit date
SNAPSHOT_DATE = '2026-10-08'           # historical evidence date
THIS_ROUND = '2026-10-15'              # dated re-check of a project's own README/source
ALLOWED_DATES = {SNAPSHOT_DATE, THIS_ROUND}
REPO_URL = 'https://github.com/IndelibleVivi/decisions-lab'
# Only the next-action experiment is implemented in this repository; every other
# entry is a recipe the caller must implement. Keep this list tight on purpose.
IMPLEMENTED_IDS = {'dev-change-next-action', 'rel-replay-threshold-coverage'}
# Project-level record of what was re-checked on 2026-10-15 (README/source only).
# A recipe whose project is here must carry THIS_ROUND; a project that was not
# re-checked keeps SNAPSHOT_DATE. Adding a project here is a deliberate claim.
VERIFIED_THIS_ROUND = {
    'https://github.com/GhalebDweikat/winnow',
    'https://github.com/NandhaKishorM/laya',
    'https://github.com/typesafe-ai/WorkflowEvals',
    'https://github.com/David-DL-Space/sys1-eval',
}
REQUIRED_KEYS = (
    'id', 'title', 'group', 'summary', 'input', 'question', 'options',
    'project', 'project_url', 'mechanism', 'first_step', 'failure_mode',
    'status', 'source_date',
)
KEBAB = re.compile(r'^[a-z0-9]+(-[a-z0-9]+)*$')
ISO_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
HEADING = re.compile(r'^(#{1,6})\s+(.*?)\s*$')


def slug(text):
    """Mirror tools/build_site.py: the anchor id a Markdown heading will get."""
    return re.sub(r'[^\w\-\u4e00-\u9fff]+', '-', text.lower()).strip('-') or 'section'


def load_recipes():
    return json.loads((ROOT / 'catalog/recipes.json').read_text(encoding='utf-8'))


class RecipeIndexTests(unittest.TestCase):
    def setUp(self):
        self.data = load_recipes()
        self.groups = self.data['groups']
        self.recipes = self.data['recipes']
        self.group_ids = [g['id'] for g in self.groups]

    def test_schema_and_shape(self):
        self.assertEqual(self.data['schema'], SCHEMA)
        self.assertEqual(self.data['updated_at'], UPDATED_AT)
        self.assertIsInstance(self.groups, list)
        self.assertIsInstance(self.recipes, list)
        # No fixed upper bound: the catalog may grow. It must at least cover the groups.
        self.assertGreaterEqual(len(self.recipes), len(self.groups))
        for group in self.groups:
            self.assertEqual(set(group), {'id', 'title'})
            self.assertTrue(group['title'].strip())
        for recipe in self.recipes:
            self.assertEqual(set(recipe), set(REQUIRED_KEYS), recipe.get('id'))
            for key in REQUIRED_KEYS:
                if key == 'options':
                    continue
                self.assertIsInstance(recipe[key], str, (recipe['id'], key))
                self.assertTrue(recipe[key].strip(), (recipe['id'], key))
            self.assertIsInstance(recipe['options'], list)

    def test_ids_unique_and_kebab_case(self):
        ids = [r['id'] for r in self.recipes]
        self.assertEqual(len(ids), len(set(ids)), 'duplicate recipe id')
        for recipe_id in ids:
            self.assertRegex(recipe_id, KEBAB, recipe_id)
            self.assertTrue(recipe_id.isascii(), recipe_id)

    def test_groups_map_to_recipes(self):
        self.assertEqual(len(self.group_ids), len(set(self.group_ids)))
        used = {r['group'] for r in self.recipes}
        self.assertTrue(used <= set(self.group_ids), used - set(self.group_ids))
        self.assertEqual(used, set(self.group_ids), 'every group must have a recipe')

    def test_options_distinct_and_offer_an_exit(self):
        for recipe in self.recipes:
            options = recipe['options']
            self.assertGreaterEqual(len(options), 3, recipe['id'])
            self.assertEqual(len(options), len(set(options)), 'duplicate option: ' + recipe['id'])
            for option in options:
                self.assertIsInstance(option, str)
                self.assertTrue(option.strip(), recipe['id'])
            joined = ' '.join(options)
            self.assertTrue(
                ('unknown' in joined) or ('需要补充' in joined) or ('都不' in joined),
                'recipe must offer an exit option: ' + recipe['id'],
            )

    def test_status_only_implemented_offline_matches_the_repository(self):
        statuses = {r['status'] for r in self.recipes}
        self.assertTrue(statuses <= {'implemented-offline', 'recipe'}, statuses)
        marked = {r['id'] for r in self.recipes if r['status'] == 'implemented-offline'}
        self.assertEqual(marked, IMPLEMENTED_IDS)
        for recipe in self.recipes:
            if recipe['status'] == 'implemented-offline':
                self.assertEqual(recipe['project_url'], REPO_URL, recipe['id'])
            else:
                self.assertEqual(recipe['status'], 'recipe')

    def test_recipe_projects_are_grounded_in_recorded_sources(self):
        repos = json.loads(
            (ROOT / 'research/2026-10-08/repositories.json').read_text(encoding='utf-8')
        )['repositories']
        repo_urls = {r['repo'] for r in repos}
        for recipe in self.recipes:
            self.assertTrue(recipe['project_url'].startswith('https://'), recipe['id'])
            if recipe['status'] == 'recipe':
                self.assertIn(recipe['project_url'], repo_urls,
                              'unknown project url: ' + recipe['id'])

    def test_source_dates_follow_the_project_recheck_map(self):
        for recipe in self.recipes:
            self.assertRegex(recipe['source_date'], ISO_DATE, recipe['id'])
            self.assertIn(recipe['source_date'], ALLOWED_DATES, recipe['id'])
            if recipe['status'] == 'implemented-offline':
                self.assertEqual(recipe['source_date'], UPDATED_AT, recipe['id'])
            elif recipe['project_url'] in VERIFIED_THIS_ROUND:
                self.assertEqual(recipe['source_date'], THIS_ROUND, recipe['id'])
            else:
                self.assertEqual(recipe['source_date'], SNAPSHOT_DATE, recipe['id'])
        # Both the historical snapshot date and this round's date must occur:
        # un-rechecked history stays dated, re-checked projects move forward.
        dates = {r['source_date'] for r in self.recipes}
        self.assertIn(SNAPSHOT_DATE, dates)
        self.assertIn(THIS_ROUND, dates)

    def test_no_private_or_account_data(self):
        text = (ROOT / 'catalog/recipes.json').read_text(encoding='utf-8')
        doc = (ROOT / 'docs/playbook.md').read_text(encoding='utf-8')
        for blob in (text, doc):
            for marker in ('/Users/', '~/', 'faye'):
                self.assertNotIn(marker, blob)


class PlaybookMarkdownTests(unittest.TestCase):
    def setUp(self):
        self.data = load_recipes()
        self.recipes = self.data['recipes']
        self.doc = (ROOT / 'docs/playbook.md').read_text(encoding='utf-8')
        self.lines = self.doc.splitlines()
        self.headings = []  # (line index, level, label, anchor id)
        for index, line in enumerate(self.lines):
            match = HEADING.match(line)
            if match:
                label = match.group(2)
                self.headings.append((index, len(match.group(1)), label, slug(label)))
        self.blocks = self._recipe_blocks()

    def _recipe_blocks(self):
        blocks, current, buf = {}, None, []
        for line in self.lines:
            if HEADING.match(line):
                if current is not None:
                    blocks[current] = buf
                current, buf = None, []
                match = HEADING.match(line)
                for recipe in self.recipes:
                    if match.group(2) == recipe['id']:
                        current = recipe['id']
                        break
            elif current is not None:
                buf.append(line)
            else:
                buf.append(line)
        if current is not None:
            blocks[current] = buf
        return blocks

    def test_recipe_headings_produce_the_real_anchor(self):
        """The site builds ids from slug(label); docs/playbook.html#<id> must resolve."""
        for recipe in self.recipes:
            matches = [h for h in self.headings if h[3] == recipe['id']]
            self.assertEqual(len(matches), 1,
                             'expected exactly one heading anchoring #%s, found %d'
                             % (recipe['id'], len(matches)))
            line_index, level, label, anchor = matches[0]
            self.assertEqual(label, recipe['id'],
                             'heading label must be the bare kebab id: ' + recipe['id'])
            self.assertGreaterEqual(level, 2)  # not the page title
            self.assertEqual(self.lines[line_index].strip(), '#' * level + ' ' + recipe['id'])

    def test_each_recipe_shows_its_chinese_title_after_the_anchor(self):
        for recipe in self.recipes:
            line_index = next(h[0] for h in self.headings if h[3] == recipe['id'])
            following = next(line.strip() for line in self.lines[line_index + 1:] if line.strip())
            self.assertEqual(following, '**%s**' % recipe['title'],
                             'missing bold Chinese title after #' + recipe['id'])

    def test_markdown_matches_json_fields(self):
        for recipe in self.recipes:
            block = '\n'.join(self.blocks[recipe['id']])
            self.assertIn(recipe['input'], block, 'input drifted: ' + recipe['id'])
            self.assertIn(recipe['question'], block, 'question drifted: ' + recipe['id'])
            for option in recipe['options']:
                self.assertIn(option, block, 'option drifted: %s / %s' % (recipe['id'], option))

    def test_document_covers_every_group(self):
        for group in self.data['groups']:
            self.assertIn(group['title'], self.doc, group['id'])

    def test_document_marks_the_split_between_proposal_and_project(self):
        self.assertIn('这不是穷尽市场', self.doc)
        for marker in ('implemented-offline', 'recipe'):
            self.assertIn(marker, self.doc)

    def test_document_links_the_dated_contract_update(self):
        link = '../research/2026-10-15/README.md'
        self.assertIn(link, self.doc)
        self.assertTrue((ROOT / 'research/2026-10-15/README.md').is_file())
        # The homepage "copy task JSON" is this project's generic task shape,
        # not a vendor-native request body.
        self.assertIn('通用任务 JSON', self.doc)

    def test_document_gives_project_start_points(self):
        self.assertIn('现成项目怎么开始', self.doc)
        for url in sorted(VERIFIED_THIS_ROUND):
            self.assertIn(url, self.doc, 'missing project entry point: ' + url)


if __name__ == '__main__':
    unittest.main()
