"""Validate built local links, fragments and the explicit publication boundary."""
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1] / '_site'


class PreviewContract(HTMLParser):
    """Check the generated UI/portable-task boundary, not a second rendering path."""
    def __init__(self):
        super().__init__()
        self.stack = []
        self.recipes = {}
        self.current = None
        self.button = None
        self.payload = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set(attrs.get('class', '').split())
        if tag == 'details' and 'recipe' in classes:
            self.current = {'options': [], 'states': set(), 'examples': set(), 'payload': ''}
            self.recipes[attrs['id']] = self.current
        if self.current is not None:
            if 'data-choice' in attrs:
                ancestors = set().union(*(entry[1] for entry in self.stack))
                self.button = dict(index=int(attrs['data-choice']), label=attrs['data-choice-label'],
                                   kind=attrs['data-choice-kind'], mark='',
                                   in_actions='recipe-options' in ancestors,
                                   in_abstention='choice-abstention' in ancestors)
                self.current['options'].append(self.button)
            if 'data-outcome-state' in attrs:
                self.current['states'].add(attrs['data-outcome-state'])
            if 'data-outcome-example' in attrs:
                self.current['examples'].add(attrs['data-outcome-example'])
            if tag == 'pre' and 'recipe-payload' in classes:
                self.payload = True
        if tag not in {'meta', 'link', 'input', 'br', 'hr', 'img', 'source', 'wbr'}:
            self.stack.append((tag, classes))

    def handle_endtag(self, tag):
        if tag == 'button':
            self.button = None
        if tag == 'pre':
            self.payload = False
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                if tag == 'details' and 'recipe' in self.stack[index][1]:
                    self.current = None
                del self.stack[index:]
                break

    def handle_data(self, data):
        if self.current is None:
            return
        if self.payload:
            self.current['payload'] += data
        if self.button is not None and self.stack and self.stack[-1][0] == 'small':
            self.button['mark'] += data


def check_preview():
    parser = PreviewContract()
    parser.feed((ROOT/'index.html').read_text(encoding='utf-8'))
    catalog = json.loads((ROOT.parent/'catalog/recipes.json').read_text())['recipes']
    assert len(parser.recipes) == len(catalog), 'Every catalog recipe needs its complete preview'
    for recipe in catalog:
        preview = parser.recipes['recipe-' + recipe['id']]
        assert preview['states'] == {'ok', 'unknown', 'refusal', 'error'}, recipe['id']
        assert preview['examples'] == {'refusal', 'error'}, recipe['id']
        task = json.loads(preview['payload'])
        assert task == {key: recipe[key] for key in ('input', 'question', 'options')}, recipe['id']
        controls = sorted(preview['options'], key=lambda option: option['index'])
        assert [option['label'] for option in controls] == recipe['options'], recipe['id']
        for option in controls:
            if option['label'] == 'unknown':
                assert option['kind'] == 'escape' and option['in_abstention'] and not option['in_actions'], recipe['id']
                assert option['mark'] == 'UNK', 'unknown cannot have an action number'
            else:
                assert option['kind'] in {'action', 'context'} and option['in_actions'], recipe['id']
                assert option['mark'] == f'{option["index"] + 1:02}', recipe['id']
            if option['label'] in {'都不适用', '该子问题不适用', '无法从分布确定', '直接拒绝'}:
                assert option['kind'] == 'action', 'A domain answer is not a request for context or API refusal'
    print(f'Checked outcome semantics, separate unknown controls and unchanged task payloads for {len(catalog)} recipes.')


class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self.ids=set()
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if 'id' in a: self.ids.add(a['id'])
        for field in ('href','src'):
            if field in a: self.links.append(a[field])

def main():
    pages={}
    for page in ROOT.rglob('*.html'):
        parser=Links(); parser.feed(page.read_text(encoding='utf-8')); pages[page]=parser
    failures=[]
    for page, parser in pages.items():
        for link in parser.links:
            u=urlsplit(link)
            if u.scheme or u.netloc: continue
            target=(page.parent/unquote(u.path)).resolve() if u.path else page
            if not target.is_relative_to(ROOT) or not target.is_file():
                failures.append(f'{page.relative_to(ROOT)}: missing/escaping {link}')
            elif u.fragment and target in pages and unquote(u.fragment) not in pages[target].ids:
                failures.append(f'{page.relative_to(ROOT)}: missing fragment {link}')
    if failures: raise SystemExit('\n'.join(failures))
    check_preview()
    print(f'Checked local links/fragments across {len(pages)} rendered pages.')

if __name__ == '__main__': main()
