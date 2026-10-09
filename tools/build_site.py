"""Build the public reader from canonical Markdown and an explicit asset allowlist."""
from __future__ import annotations
import argparse
import html
import hashlib
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
ASSETS = ('LICENSE', 'site/style.css', 'site/filter.js', 'site/reader.js', 'site/lab.js', 'site/flow.svg',
          'catalog/index.json', 'experiments/next-action/cases.json') + tuple(
              'research/2026-10-08/' + p for p in SNAPSHOT_FILES)


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


PAGE_CONTEXT = {
    'README.html': ('00', '开始使用', 'Guide'),
    'README.en.html': ('00', 'Getting started', 'Guide'),
    'research/2026-10-08/README.html': ('01', '研究档案', 'Research'),
    'research/2026-10-08/report.html': ('01', '决策 API 调查', 'Research'),
    'docs/projects.html': ('02', '相关项目', 'Directory'),
    'experiments/next-action/README.html': ('03', 'Next-action 实验', 'Experiment'),
    'docs/method.html': ('04', '评估方法', 'Method'),
    'docs/integration.html': ('05', '工作流接入', 'Integration'),
    'docs/maintenance.html': ('06', '维护与更新', 'Maintenance'),
    'docs/current-state.html': ('07', '当前状态', 'Status'),
    'LICENSING.html': ('08', '许可与归属', 'Colophon'),
    'LICENSE-DOCUMENTATION.html': ('08', '文档许可', 'Colophon'),
}


def shell(title, body, current, toc=()):
    prefix = '../' * current.count('/')
    def asset(path):
        # Bind browser caches to the actual public asset, including local rebuilds.
        version = hashlib.sha256((ROOT/path).read_bytes()).hexdigest()[:12]
        return prefix + path + '?v=' + version
    is_home = current == 'index.html'
    is_en = current == 'README.en.html'
    number, section, english = PAGE_CONTEXT.get(current, ('00', '研究索引', 'Index'))
    nav_items = (('index.html', '索引'), ('research/2026-10-08/README.html', '研究'),
                 ('docs/projects.html', '项目'), ('experiments/next-action/README.html', '实验'),
                 ('docs/method.html', '方法'))
    nav = ''.join(f'<a href="{prefix}{path}"' +
                  (' aria-current="page"' if current == path or (path.startswith('research/') and current.startswith('research/')) else '') +
                  f'>{label}</a>' for path, label in nav_items)
    toc = [(anchor, re.sub(r'^\d{2}\s*[·.]\s*', '', label)) for anchor, label in toc]
    entries = ''.join(f'<a href="#{html.escape(anchor)}"><span>{i:02}</span>{html.escape(label)}</a>'
                      for i, (anchor, label) in enumerate(toc, 1))
    toc_html = f'<details class="mobile-contents toc-details"><summary>本页目录 <span>{len(toc):02} 节</span></summary><nav class="toc" aria-label="本页目录">{entries}</nav></details>' if toc else ''
    sidebar = f'<aside class="reading-rail"><a class="back-index" href="{prefix}index.html">← 研究索引</a><p class="rail-label">{english.upper()} / {number}</p><nav class="toc" aria-label="章节导航">{entries}</nav><div class="rail-bottom"><a href="{prefix}{current.removesuffix(".html")}.md">Markdown ↗</a></div></aside>'
    # Source links go to the canonical public repository; Markdown is not duplicated in the site.
    sidebar = sidebar.replace(f'href="{prefix}{current.removesuffix(".html")}.md"', f'href="https://github.com/IndelibleVivi/decisions-lab/blob/main/{current.removesuffix(".html")}.md"')
    if not is_home:
        body = f'<div class="page-heading"><span>{number} / {section}</span><span>{english.upper()}</span></div>{toc_html}<div class="reading-layout">{sidebar}<article>{body}</article></div>'
    lab_script = f'<script defer src="{asset("site/lab.js")}"></script>' if is_home else ''
    return f'''<!doctype html>
<html lang="{'en' if is_en else 'zh-CN'}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)} · Decisions Lab</title><meta name="description" content="决策模型、API 契约和可复现实验。"><meta name="theme-color" content="#f1f0f4"><link rel="icon" href="data:,"><link rel="stylesheet" href="{asset('site/style.css')}"><script defer src="{asset('site/filter.js')}"></script><script defer src="{asset('site/reader.js')}"></script>{lab_script}</head>
<body class="{'is-home' if is_home else 'is-reader'}"><a class="skip" href="#content">{'Skip to content' if is_en else '跳到正文'}</a>
<header class="site-header"><a class="brand" href="{prefix}index.html" aria-label="Decisions Lab 首页"><span class="brand-symbol" aria-hidden="true">d.</span><span>Decisions Lab</span></a><nav class="primary-nav" aria-label="主导航">{nav}</nav><div class="header-links"><a href="https://github.com/IndelibleVivi/decisions-lab">GitHub ↗</a><a href="{prefix}{'README.html' if is_en else 'README.en.html'}" lang="{'zh' if is_en else 'en'}">{'中文' if is_en else 'EN'}</a></div><div class="reading-progress" aria-hidden="true"></div></header>
<main id="content" class="{'landing' if is_home else 'reader'}">{body}</main>
<footer class="site-footer"><a class="footer-name" href="{prefix}index.html">Decisions Lab<span>有限判断的研究与实践</span></a><div><a href="{prefix}docs/maintenance.html">维护方式</a><a href="{prefix}docs/current-state.html">当前状态</a><a href="{prefix}LICENSING.html">许可与来源</a></div><p>METHODS ENDURE.<br>EVIDENCE HAS A DATE.</p></footer></body></html>'''


def home():
    metadata = json.loads((ROOT/'research/2026-10-08/metadata.json').read_text())
    results = json.loads((ROOT/'research/2026-10-08/reanalysis/sys1_reanalysis.json').read_text())['results']
    measurements = []
    for key, code, name in (('A_model_router', 'A', '模型路由'), ('B_tool_selection', 'B', '工具选择'), ('F_cardinality_multilingual', 'F', '高候选数 / 多语单选')):
        row, score = results[key], results[key]['jev']
        percentage = score['original_accuracy'] * 100
        measurements.append(f'''<div class="measurement"><div class="measurement-name"><span>{code}</span>{name}</div><p class="measurement-value">{percentage:g}<span>%</span></p><div class="measurement-track" aria-hidden="true"><span style="width:{percentage:g}%"></span></div><p class="measurement-count">{score['original_correct']} / {row['cases']} 判断正确</p><p class="measurement-note">高 maxP 中错误 <strong>{score['high_confidence_errors']} / {score['high_confidence_n']}</strong></p></div>''')
    suite = json.loads((ROOT/'experiments/next-action/cases.json').read_text())
    ids = ('relnote-field-zh', 'missing-doc-placeholder-zh', 'changelog-breaking-zh')
    cases = [next(c for c in suite['cases'] if c['id'] == wanted) for wanted in ids]
    payload = json.dumps(cases, ensure_ascii=False).replace('<', '\\u003c')
    initial = cases[0]
    task = initial['task']
    def fragment(text):
        return MarkdownIt('commonmark', {'html': False}).renderInline(text)
    actions = [('inspect_source', '核对来源', '01'), ('compare_contract', '比较契约', '02'),
               ('read_in_context', '结合上下文阅读', '03'), ('needs_more_context', '先补信息', '04'),
               ('unknown', '没有合适选项', '05')]
    buttons = ''.join(f'<button type="button" data-action="{key}"><span>{num}</span>{label}<span class="choice-arrow" aria-hidden="true">↗</span></button>' for key, label, num in actions)
    return f'''<section class="masthead" aria-labelledby="site-title"><div class="masthead-meta"><span>独立研究 / 开放记录</span><span>VOL. 01 — OCT 2026</span></div><h1 id="site-title">Decisions <em>Lab</em><span class="title-period">.</span></h1><div class="masthead-bottom"><p>决策模型 · 接口契约 · 可复现实验</p><a href="README.html">关于这个项目 <span>↗</span></a></div></section>
<section class="evidence-feature" aria-labelledby="evidence-title"><div class="feature-heading"><div><p class="kicker">观察 001 / HISTORICAL EVIDENCE</p><h2 id="evidence-title">同一个模型，<br>为什么差这么多？</h2></div><div class="feature-summary"><p>判断的质量，取决于具体任务。<br>从三组历史结果，重新认识“高置信度”。</p><a href="research/2026-10-08/report.html">进入研究 <span>↗</span></a></div></div><div class="measurements">{''.join(measurements)}</div><div class="evidence-caption"><span>Jev · 历史数据复算</span><p>maxP ≥ 0.9；各任务样本与条件不同。数据来自 sys1-eval，不是当前模型排名。</p><a href="research/2026-10-08/README.html">来源与复算 ↗</a></div></section>
<section class="index-section" aria-labelledby="index-title"><div class="section-heading"><h2 id="index-title">继续调查<span>THE INDEX</span></h2><p>沿着一个问题，找到下一份证据。</p></div><div class="index-rows">
<a class="index-row" href="research/2026-10-08/report.html"><span class="index-no">01</span><h3>决策 API，究竟承诺了什么？</h3><p>原生接口、托管路线与开放模型</p><span class="index-meta">{metadata['research_entities']} 个实体</span><span class="row-arrow">↗</span></a>
<a class="index-row" href="docs/projects.html"><span class="index-no">02</span><h3>有哪些项目，值得真正拆开？</h3><p>SDK、决策头、运行时与评测</p><span class="index-meta">{metadata['repository_index_entries']} 个项目</span><span class="row-arrow">↗</span></a>
<a class="index-row" href="docs/method.html"><span class="index-no">03</span><h3>怎样分辨，一个判断是否可靠？</h3><p>正确率、覆盖率、校准与错误代价</p><span class="index-meta">评估方法</span><span class="row-arrow">↗</span></a>
<a class="index-row" href="docs/integration.html"><span class="index-no">04</span><h3>然后，把判断接进工作流。</h3><p>从离线回放到旁路建议</p><span class="index-meta">接入设计</span><span class="row-arrow">↗</span></a></div></section>
<section class="decision-exercise" aria-labelledby="exercise-title"><div class="section-heading"><h2 id="exercise-title">轮到你判断<span>EXPERIMENT 01</span></h2><p>合成用例 · 浏览器内完成 · 无模型调用</p></div><div class="exercise-layout"><div class="specimen"><div class="specimen-top"><span>阅读材料</span><label class="case-selector" hidden>切换用例 <select id="sample-case"><option value="0">01 / 字段更名</option><option value="1">02 / 信息缺失</option><option value="2">03 / 默认值变化</option></select></label></div><p id="sample-document">{fragment(task['document'])}</p><div class="claim"><span>待核对的主张</span><p id="sample-claim">{fragment(task['claim'])}</p></div><p class="sample-source">原创合成输入；来源地址为占位符。</p></div><div class="exercise-actions" hidden><p class="action-prompt">下一步，你会先做什么？</p><div class="choice-list">{buttons}</div><div id="sample-feedback" role="status" aria-live="polite"><span>选择一个动作，查看编辑标签与理由。</span></div></div><noscript><p class="no-script">启用 JavaScript 可在本页选择动作；也可以直接<a href="experiments/next-action/README.html">阅读完整实验</a>。</p></noscript></div><div class="exercise-footer"><p>{len(suite['cases'])} 个合成案例，允许多个合理动作。人工标签可讨论，不等于模型实测。</p><a href="experiments/next-action/README.html">运行完整实验 <span>↗</span></a></div><script id="sample-data" type="application/json">{payload}</script></section>
<section class="archive-strip"><span class="archive-symbol" aria-hidden="true">↳</span><h2>信息会变。<br>把证据留下。</h2><div><p>方法持续修订，调查按日期保存。<br>每一次实验，都有可以重新打开的记录。</p><a href="docs/maintenance.html">我们怎样维护这份研究 ↗</a></div><p class="archive-date">2026<br><span>10.08</span><small>首期研究截点</small></p></section>'''


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
            body = body.replace('</h1>', '</h1><div class="filter" hidden><label for="project-filter">查找项目或机制</label><div class="filter-field"><input id="project-filter" type="search" placeholder="calibration、Laya、SDK…"><button id="filter-clear" type="button">清空</button></div><p id="filter-result" role="status"></p><nav id="filter-matches" aria-label="匹配项目，可跳到表格行" hidden></nav></div>', 1)
        dest = rel.removesuffix('.md')+'.html'
        (output/dest).parent.mkdir(parents=True, exist_ok=True)
        (output/dest).write_text(shell(title, body.replace('<table>', '<div class="table-wrap" tabindex="0" role="region" aria-label="数据表，可横向滚动"><table>').replace('</table>', '</table></div>'), dest, toc), encoding='utf-8')
    (output/'index.html').write_text(shell('研究索引', home(), 'index.html'), encoding='utf-8')
    print(f'Built {len(PAGES)+1} pages in _site/ (explicit public allowlist; no network).')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    build(ROOT/'_site')
