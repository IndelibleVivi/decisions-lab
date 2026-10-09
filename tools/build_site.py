"""Build the public reader from canonical Markdown and an explicit asset allowlist."""
from __future__ import annotations
import argparse
import html
import json
import posixpath
import re
import shutil
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit
from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[1]
PAGES = (
    'README.md', 'README.en.md', 'LICENSING.md', 'LICENSE-DOCUMENTATION.md',
    'docs/projects.md', 'docs/method.md', 'docs/integration.md',
    'docs/maintenance.md', 'docs/current-state.md',
    'experiments/next-action/README.md',
    'research/2026-10-08/README.md', 'research/2026-10-08/report.md',
)
SNAPSHOT_FILES = (
    'calculations.json', 'calculations.py', 'census.json', 'llamacpp_route.json',
    'metadata.json', 'openai_decisions_record.json', 'openrouter_routes.json',
    'practice_evidence.json', 'public_probe_protocol.json', 'repositories.json',
    'source_index.json', 'verification.json', 'report_verification.json',
    'watchlist.json', 'import-manifest.json', 'reanalysis/author_numbers.json',
    'reanalysis/provenance.json', 'reanalysis/recompute_sys1.py',
    'reanalysis/sys1_reanalysis.json',
)
ASSETS = ('LICENSE', 'site/style.css', 'site/filter.js', 'site/flow.svg',
          'catalog/index.json', 'experiments/next-action/cases.json') + tuple(
              'research/2026-10-08/' + p for p in SNAPSHOT_FILES)
NAV = (('index.html','首页'), ('research/2026-10-08/README.html','研究'),
       ('docs/projects.html','项目'), ('experiments/next-action/README.html','实验'),
       ('docs/integration.html','接入'))


def slug(text):
    return re.sub(r'[^\w\-\u4e00-\u9fff]+', '-', text.lower()).strip('-') or 'section'


def render_markdown(source, current):
    md = MarkdownIt('commonmark', {'html': False}).enable('table')
    tokens = md.parse(source)
    toc, used = [], set()
    title = 'Decisions Lab'
    for i, token in enumerate(tokens):
        if token.type == 'heading_open':
            label = tokens[i+1].content
            anchor = slug(label)
            base, n = anchor, 2
            while anchor in used:
                anchor, n = f'{base}-{n}', n+1
            used.add(anchor)
            token.attrSet('id', anchor)
            if token.tag == 'h1': title = label
            elif token.tag == 'h2': toc.append((anchor, label))
        for child in token.children or []:
            if child.type == 'link_open':
                value = child.attrGet('href')
                u = urlsplit(value)
                if not u.scheme and not u.netloc and u.path:
                    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(current), unquote(u.path)))
                    if resolved in PAGES:
                        child.attrSet('href', urlunsplit(('', '', u.path.removesuffix('.md')+'.html',u.query,u.fragment)))
    return title, md.renderer.render(tokens, md.options, {}), toc


def shell(title, body, current, toc=()):
    prefix = '../' * current.count('/')
    nav = ''.join(f'<a href="{prefix}{p}"'+(' aria-current="page"' if p == current else '')+f'>{t}</a>' for p,t in NAV)
    contents = ''.join(f'<a href="#{html.escape(a)}">{html.escape(t)}</a>' for a,t in toc)
    return f'''<!doctype html><html lang="{'en' if current == 'README.en.html' else 'zh-CN'}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)} · Decisions Lab</title><meta name="description" content="决策模型、API 契约和可复现实验。"><link rel="icon" href="data:,"><link rel="stylesheet" href="{prefix}site/style.css"><script defer src="{prefix}site/filter.js"></script></head><body><a class="skip" href="#content">跳到正文</a><header><a class="brand" href="{prefix}index.html"><span class="mark" aria-hidden="true">⌁</span> DECISIONS LAB</a><nav aria-label="主导航">{nav}</nav><a class="language" href="{prefix}README.en.html" lang="en">EN ↗</a></header><main id="content" class="{'landing' if current == 'index.html' else 'reader'}">{body}</main>{f'<aside class="toc" aria-label="本页目录"><span>ON THIS PAGE</span>{contents}</aside>' if contents else ''}<footer><span>Decisions Lab · 可检查的判断</span><a href="{prefix}LICENSING.html">许可与来源</a><a href="{prefix}docs/current-state.html">当前状态</a><span>研究截点 2026-10-08</span></footer></body></html>'''


def home():
    data = json.loads((ROOT/'research/2026-10-08/metadata.json').read_text())
    return f'''<section class="hero"><div class="eyebrow"><span class="dot"></span> RESEARCH / CONTRACTS / EXPERIMENTS</div><h1>每一次判断，<br>都值得<span class="accent">被检查。</span></h1><div class="hero-bottom"><p>决策模型正在进入软件。<br>这里保存它们的承诺、证据与失误，<br>也实验下一步，究竟该往哪里走。</p><a class="primary" href="experiments/next-action/README.html">运行第一个实验 <span>↗</span></a></div><div class="branch" aria-hidden="true"><svg viewBox="0 0 430 340"><path d="M15 170H125Q155 170 175 140L245 45H407M125 170Q155 170 175 195L245 290H407M170 170H407"/><circle cx="15" cy="170" r="7"/><circle cx="407" cy="45" r="7"/><circle cx="407" cy="170" r="9" class="chosen"/><circle cx="407" cy="290" r="7"/></svg><span class="branch-note">EVIDENCE → CHOICE → REVIEW</span></div></section>
<section class="issue"><span>FIELD NOTES / 001</span><span>2026.10.08</span><p>第一期调查：<strong>{data['research_entities']}</strong> 个实体 · <strong>{data['repository_index_entries']}</strong> 个项目 · <strong>{data['source_urls']}</strong> 条来源</p><a href="research/2026-10-08/report.html">阅读完整研究 →</a></section>
<section class="paths" aria-labelledby="paths"><div class="section-intro"><span class="eyebrow">THREE WAYS IN</span><h2 id="paths">从问题进入。</h2><p>找到资料只是开始。<br>把它变成可比较、可重放的证据。</p></div><div class="path-list"><a href="research/2026-10-08/README.html"><span class="number">01</span><div><h3>读清楚，一个领域</h3><p>原生 API、托管路线、开放模型。带日期与边界的研究快照。</p></div><span>↗</span></a><a href="docs/projects.html"><span class="number">02</span><div><h3>找到，值得拆开的机制</h3><p>从 SDK、决策头、运行时、工作流到评测，按用途浏览项目。</p></div><span>↗</span></a><a href="experiments/next-action/README.html"><span class="number">03</span><div><h3>运行，然后看见错误</h3><p>25 个合成案例。baseline、record、replay 与明确的 unknown。</p></div><span>↗</span></a></div></section>
<section class="experiment"><div><span class="eyebrow">EXPERIMENT 01 / NEXT ACTION</span><h2>新材料到了。<br>下一步，先核对什么？</h2><p>给定文档与任务上下文，推荐一个阅读或核对动作。<br>保留理由的边界，让人决定是否采用。</p><a href="docs/integration.html">查看接入思路 →</a></div><div class="terminal"><span>OFFLINE · NO API KEY</span><pre><code>python3 -m decision_lab validate
python3 -m decision_lab demo \\\n  --run-dir runs/demo-001
python3 -m decision_lab replay \\\n  runs/demo-001</code></pre><p>合成演示包含错误与 unknown，<br>不代表任何模型的实测表现。</p></div></section><section class="last-note"><h2>信息会变，证据要留得住。</h2><p>方法持续修订。调查按日期保存。实验每次留下新记录。</p><a href="docs/maintenance.html">了解维护方式 →</a></section>'''


def build(output):
    output = Path(output).resolve()
    # A fixed derived destination prevents accidental writes into source directories.
    if output != ROOT/'_site':
        raise ValueError('output must be the repository _site directory')
    if output.is_symlink(): raise ValueError('refuse symlink output')
    allowed = set(ASSETS) | {p.removesuffix('.md')+'.html' for p in PAGES} | {'index.html'}
    if output.exists():
        for entry in output.rglob('*'):
            if entry.is_symlink() or (entry.is_file() and entry.relative_to(output).as_posix() not in allowed):
                raise ValueError(f'Unexpected existing output; inspect before rebuilding: {entry.relative_to(output)}')
    output.mkdir(exist_ok=True)
    for rel in ASSETS:
        source, target = ROOT/rel, output/rel
        if source.is_symlink(): raise ValueError(f'refuse symlink source: {rel}')
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink(): raise ValueError(f'refuse symlink output: {rel}')
        shutil.copyfile(source, target)
    for rel in PAGES:
        title, body, toc = render_markdown((ROOT/rel).read_text(encoding='utf-8'), rel)
        if rel == 'docs/projects.md':
            # Progressive enhancement; all research remains readable without JavaScript.
            body = '<div class="filter" hidden><label for="project-filter">在项目地图中查找</label><input id="project-filter" type="search" placeholder="试试 calibration、Laya、SDK…"><p id="filter-result" role="status"></p></div>' + body
        dest = rel.removesuffix('.md')+'.html'
        (output/dest).parent.mkdir(parents=True, exist_ok=True)
        (output/dest).write_text(shell(title, '<article>'+body+'</article>', dest, toc), encoding='utf-8')
    (output/'index.html').write_text(shell('每一次判断，都值得被检查', home(), 'index.html'), encoding='utf-8')
    print(f'Built {len(PAGES)+1} pages in _site/ (explicit public allowlist; no network).')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    build(ROOT/'_site')
