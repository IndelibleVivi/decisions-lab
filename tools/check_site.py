"""Validate built local links, fragments and the explicit publication boundary."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1] / '_site'
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
    print(f'Checked local links/fragments across {len(pages)} rendered pages.')

if __name__ == '__main__': main()
