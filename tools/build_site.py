"""Build the public reader from canonical Markdown and an explicit asset allowlist."""
from __future__ import annotations
import argparse
import html
import hashlib
import json
import math
import posixpath
import re
import shutil
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit
from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[1]
LATEST_UPDATE = json.loads((ROOT / 'catalog/index.json').read_text(encoding='utf-8'))['latest_update']
LATEST_UPDATE_PAGE = LATEST_UPDATE['reader'].removesuffix('.md') + '.html'
PAGES = (
    'README.md', 'README.en.md', 'LICENSING.md', 'LICENSE-DOCUMENTATION.md',
    'docs/projects.md', 'docs/playbook.md', 'docs/method.md', 'docs/integration.md',
    'docs/research-infrastructure.md', 'experiments/generated/README.md', 'experiments/comparison/README.md',
    'docs/maintenance.md', 'docs/current-state.md', 'docs/typed-values.md', 'docs/api-capabilities.md',
    'experiments/next-action/README.md',
    'experiments/typed-values/README.md', 'experiments/api-capabilities/README.md',
    'experiments/provider-pilot/README.md',
    'experiments/provider-pilot/luna-followup-2026-10-24.md',
    'experiments/decision-roles/README.md',
    'research/2026-10-08/README.md', 'research/2026-10-08/report.md', 'research/2026-10-15/README.md',
    'research/2026-10-20/README.md', 'research/2026-10-22/README.md',
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
ASSETS = ('LICENSE', 'site/style.css', 'site/filter.js', 'site/reader.js', 'site/lab.js', 'site/field.js', 'site/evidence.js', 'site/sculpture.js', 'site/atlas.js', 'site/theme.js', 'site/flow.svg',
          'experiments/api-capabilities/suite.json', 'experiments/api-capabilities/example-responses.json',
          'catalog/capabilities.json', 'research/2026-10-22/updates.json', 'research/2026-10-22/public_probe_protocol.json',
          'catalog/index.json', 'catalog/recipes.json', 'research/2026-10-15/updates.json', 'research/2026-10-20/updates.json', 'experiments/typed-values/examples.json', 'site/recipes.js', 'site/pixels.js', 'site/lettering.js', 'site/motion.js', 'experiments/next-action/cases.json') + tuple(
              'site/fonts/' + f for f in ('OFL-1.1.txt', 'README.md',
                                          'space-grotesk-500-latin.woff2', 'space-grotesk-500-latin-ext.woff2',
                                          'space-grotesk-600-latin.woff2', 'space-grotesk-600-latin-ext.woff2',
                                          'space-grotesk-700-latin.woff2', 'space-grotesk-700-latin-ext.woff2',
                                          'silkscreen-400-latin.woff2', 'silkscreen-400-latin-ext.woff2',
                                          'silkscreen-700-latin.woff2', 'silkscreen-700-latin-ext.woff2')) + tuple(
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
    body = md.renderer.render(tokens, md.options, {})
    if current == 'docs/playbook.md':
        # Stable Markdown IDs keep deep links portable; show the reader's title
        # once in HTML instead of promoting a machine ID to the visual heading.
        for recipe in json.loads((ROOT/'catalog/recipes.json').read_text())['recipes']:
            key, name = html.escape(recipe['id']), html.escape(recipe['title'])
            body = body.replace(f'<h3 id="{key}">{key}</h3>\n<p><strong>{name}</strong></p>',
                                f'<h3 id="{key}">{name}</h3>')
    return title, body, toc


PAGE_CONTEXT = {
    'README.html': ('00', '开始使用', 'Guide'),
    'README.en.html': ('00', 'Getting started', 'Guide'),
    'research/2026-10-08/README.html': ('01', '研究档案', 'Research'),
    'research/2026-10-08/report.html': ('01', '决策 API 调查', 'Research'),
    'docs/projects.html': ('02', '相关项目', 'Directory'),
    'docs/playbook.html': ('09', '妙妙玩法', 'Playbook'),
    'research/2026-10-15/README.html': ('01', '10 月增量核查', 'Research update'),
    'research/2026-10-22/README.html': ('01', 'API 能力与实验', 'Research update'),
    'docs/research-infrastructure.html': ('14', '研究基础设施', 'Research tools'),
    'experiments/generated/README.html': ('15', '有限世界与规则修复', 'Synthetic workflow'),
    'experiments/comparison/README.html': ('16', '配对比较与统计', 'Analysis'),
    'experiments/provider-pilot/README.html': ('17', '原生模型首轮实验', 'Provider experiment'),
    'experiments/provider-pilot/luna-followup-2026-10-24.html': ('18', 'Luna 补充实验', 'Luna follow-up'),
    'experiments/decision-roles/README.html': ('19', '决策角色实验', 'Decision roles'),
    'docs/api-capabilities.html': ('12', 'API 能力研究', 'Capabilities'),
    'experiments/api-capabilities/README.html': ('13', 'API 能力实验', 'Offline experiment'),
    'research/2026-10-20/README.html': ('01', 'Clairic 与类型化取值', 'Research update'),
    'experiments/next-action/README.html': ('03', 'Next-action 实验', 'Experiment'),
    'experiments/typed-values/README.html': ('11', '类型化取值实验', 'Offline experiment'),
    'docs/typed-values.html': ('10', '类型化输出', 'Typed values'),
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
    nav_items = (('index.html', '索引'), (LATEST_UPDATE_PAGE, '更新'), ('docs/playbook.html', '玩法'),
                 ('docs/projects.html', '项目'), ('experiments/api-capabilities/README.html', '实验'),
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
    lab_script = ''.join(f'<script defer src="{asset(path)}"></script>' for path in ('site/sculpture.js', 'site/atlas.js', 'site/field.js', 'site/evidence.js', 'site/lab.js', 'site/recipes.js', 'site/pixels.js', 'site/motion.js', 'site/lettering.js')) if is_home else ''
    return f'''<!doctype html>
<html lang="{'en' if is_en else 'zh-CN'}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)} · Decisions Lab</title><meta name="description" content="决策模型、API 契约和可复现实验。"><meta name="theme-color" content="#f6f2e9"><script src="{asset('site/theme.js')}"></script><link rel="icon" href="data:,"><link rel="stylesheet" href="{asset('site/style.css')}"><script defer src="{asset('site/filter.js')}"></script><script defer src="{asset('site/reader.js')}"></script>{lab_script}<noscript><style>.evidence-pixels{{display:none}}.evidence-stage{{display:block}}</style></noscript></head>
<body class="{'is-home' if is_home else 'is-reader'}"><a class="skip" href="#content">{'Skip to content' if is_en else '跳到正文'}</a>
<header class="site-header"><a class="brand" href="{prefix}index.html" aria-label="Decisions Lab 首页"><span class="brand-symbol" aria-hidden="true">{pixel_mark()}</span><span>decisions<span class="brand-slash">/</span>lab</span></a><nav class="primary-nav" aria-label="主导航">{nav}</nav><div class="header-links"><a href="https://github.com/IndelibleVivi/decisions-lab">GitHub ↗</a><a href="{prefix}{'README.html' if is_en else 'README.en.html'}" lang="{'zh' if is_en else 'en'}">{'中文' if is_en else 'EN'}</a><button id="theme-toggle" type="button" hidden aria-label="切换到夜间模式" aria-pressed="false"><i aria-hidden="true"></i><span>NIGHT</span></button></div><div class="reading-progress" aria-hidden="true"></div></header>
<main id="content" class="{'landing' if is_home else 'reader'}">{body}</main>
<footer class="site-footer"><a class="footer-name" href="{prefix}index.html">Decisions Lab<span>有限判断的研究与实践</span></a><div><a href="{prefix}docs/maintenance.html">维护方式</a><a href="{prefix}docs/current-state.html">当前状态</a><a href="{prefix}LICENSING.html">许可与来源</a></div><p>METHODS ENDURE.<br>EVIDENCE HAS A DATE.</p></footer></body></html>'''


def pixel_mark():
    rows = ('1100011', '1100011', '0010100', '0001000', '0001000', '0011100', '0011100')
    rects = ''.join(f'<rect x="{x*4}" y="{y*4}" width="3" height="3"/>' for y,row in enumerate(rows) for x,c in enumerate(row) if c=='1')
    return f'<svg viewBox="0 0 28 28" fill="currentColor" aria-hidden="true">{rects}</svg>'


def field_fallback():
    cells = []
    peaks = ((-.5,-.3),(.48,-.28),(.04,.53))
    colors = ('#244fc6','#da7766','#2f8576')
    for y in range(55):
        for x in range(55):
            u,v = (x/54-.5)*2.5,(y/54-.5)*2.5
            fields = [math.exp(-7*((u-a)**2+(v-b)**2)) for a,b in peaks]
            if max(fields)<.035: continue
            parts = [a*b for a,b in zip(fields,(.72,.2,.08))]
            px = 600+(u-v)*306
            py = 307+(u+v)*63-sum(parts)*344
            color = colors[parts.index(max(parts))]
            cells.append(f'<rect x="{px:.1f}" y="{py:.1f}" width="2.5" height="2.5" fill="{color}"/>')
    return f'<svg class="field-fallback" viewBox="0 0 1200 420" role="img" aria-label="示意概率地形，A 72%、B 20%、C 8%，并非真实模型输出">{"".join(cells)}</svg>'


def sculpture_fallback():
    # A lower-resolution still of the same original tubular trefoil.
    points = []
    def rotate(p):
        x = p[0]*math.cos(-.44)-p[1]*math.sin(-.44)
        y = p[0]*math.sin(-.44)+p[1]*math.cos(-.44)
        return (x*.93+p[2]*.367, y*.88-(p[2]*.93-x*.367)*.475,
                y*.475+(p[2]*.93-x*.367)*.88)
    for i in range(210):
        t = i/210*math.tau
        r, a = 2+math.cos(3*t), 2*t
        c = (r*math.cos(a), r*math.sin(a), math.sin(3*t))
        d = (-3*math.sin(3*t)*math.cos(a)-2*r*math.sin(a),
             -3*math.sin(3*t)*math.sin(a)+2*r*math.cos(a), 3*math.cos(3*t))
        length = math.hypot(*d)
        d = tuple(v/length for v in d)
        length = math.hypot(d[0],d[1])
        n = (d[1]/length,-d[0]/length,0)
        bi = (-d[2]*n[1],d[2]*n[0],d[0]*n[1]-d[1]*n[0])
        for j in range(24):
            v = j/24*math.tau
            normal = tuple(n[k]*math.cos(v)+bi[k]*math.sin(v) for k in range(3))
            point = rotate(tuple(c[k]+normal[k]*.47 for k in range(3)))
            lit = rotate(normal)
            light = max(0,-lit[0]*.4-lit[1]*.6+lit[2]*.7)
            x,y,z = point
            depth = .83+z*.035
            points.append((z,f'<rect x="{600+x*125*depth:.1f}" y="{400+y*125*depth:.1f}" width="3.5" height="3.5" opacity="{.3+.7*light:.2f}"/>'))
    cells = ''.join(cell for _,cell in sorted(points))
    return f'<svg class="sculpture-fallback" viewBox="0 0 1200 800" aria-hidden="true" fill="currentColor">{cells}</svg>'


def project_atlas():
    catalog = json.loads((ROOT/'catalog/index.json').read_text())
    repositories = {r['id']: r for r in json.loads((ROOT/'research/2026-10-08/repositories.json').read_text())['repositories']}
    controls, panels = [], []
    names = ('SDK', 'MODELS', 'RUNTIME', 'WORKFLOWS', 'EVALS')
    repo_names = [r['repo'].removesuffix('/').split('/')[-1] for r in repositories.values()]
    def project_name(record):
        parts = record['repo'].removesuffix('/').split('/')
        return '/'.join(parts[-2:]) if repo_names.count(parts[-1]) > 1 else parts[-1]
    for i, group in enumerate(catalog['groups']):
        label = html.escape(group['title'])
        controls.append(f'<button type="button" data-atlas-group="{group["id"]}" data-label="{label}" aria-pressed="{str(i==0).lower()}"><span>0{i+1}</span>{names[i]}</button>')
        links = ''.join(f'<a href="docs/projects.html#{slug(group["title"])}">{html.escape(project_name(repositories[r]))}<span aria-hidden="true">↗</span></a>' for r in group['projects'])
        hidden = ' hidden' if i else ''
        panels.append(f'<div data-atlas-panel="{group["id"]}"{hidden}><h2>{label}</h2><p>{html.escape(group["question"])}</p><div class="atlas-projects">{links}</div></div>')
    return f'<div id="project-atlas"><div class="atlas-controls" role="group" aria-label="探索项目类别" hidden>{"".join(controls)}</div><div class="atlas-panels">{"".join(panels)}<a class="atlas-all" href="docs/projects.html">全部项目与来源 ↗</a></div><p id="atlas-status" class="sr-only" role="status"></p></div>'


PIXEL_GLYPHS = {
    'reading-research': ('011101110','010010010','010010010','011010110','010010010','010010010','011101110','000010000','000000000'),
    'dev-agent': ('000010000','001010100','010010010','100010001','010010010','001010100','000010000','000000000','000000000'),
    'knowledge': ('000111000','000101000','011111110','010000010','110111011','100101001','110111011','000000000','000000000'),
    'creative-interactive': ('001111100','010000010','100000001','101010101','100000001','100111001','010000010','001111100','000000000'),
    'life-choice': ('000000000','001101100','011111110','011111110','001111100','000111000','000010000','000000000','000000000'),
    'reliability-lab': ('000111000','000101000','000101000','001000100','010101010','010010010','011111110','000000000','000000000'),
}


def pixel_glyph(kind):
    """Original 9×9 glyphs: identity/wayfinding, never quantitative evidence."""
    rows = PIXEL_GLYPHS.get(kind, PIXEL_GLYPHS['dev-agent'])
    pixels = ''.join(f'<rect x="{x*3}" y="{y*3}" width="3" height="3"/>' for y,row in enumerate(rows) for x,c in enumerate(row) if c=='1')
    return f'<svg class="pixel-glyph" viewBox="0 0 27 27" fill="currentColor" aria-hidden="true" shape-rendering="crispEdges">{pixels}</svg>'


def pixel_word(word):
    alphabet = {'P':('11110','10001','11110','10000','10000','10000','10000'), 'L':('10000','10000','10000','10000','10000','10000','11111'), 'A':('01110','10001','10001','11111','10001','10001','10001'), 'Y':('10001','10001','01010','00100','00100','00100','00100')}
    pixels = ''.join(f'<rect x="{i*6+x}" y="{y}" width="1" height="1"/>' for i,c in enumerate(word) for y,row in enumerate(alphabet[c]) for x,v in enumerate(row) if v=='1')
    return f'<svg class="pixel-word" viewBox="0 0 {len(word)*6-1} 7" fill="currentColor" aria-hidden="true" shape-rendering="crispEdges">{pixels}</svg>'


def option_kind(option):
    """Presentation metadata, never a rewrite of the catalog's offered values."""
    if option == 'unknown':
        return 'escape'
    # A domain answer such as 都不适用 / 无法从分布确定 is still an ordinary
    # choice. Only requests for material or human review use the return path.
    if any(marker in option for marker in ('需要', '需补', '人工', '材料不足', '送人复核', '先补')):
        return 'context'
    return 'action'


def recipe_explorer():
    book = json.loads((ROOT/'catalog/recipes.json').read_text())
    escape = html.escape
    tabs = '<button type="button" data-recipe-group="all" aria-pressed="true">全部</button>' + ''.join(
        f'<button type="button" data-recipe-group="{escape(g["id"])}" aria-pressed="false">{pixel_glyph(g["id"])}{escape(g["title"])}</button>' for g in book['groups'])
    def endpoint(kinds, index):
        # Mirrors endpoint() in site/pixels.js so the static SVG matches the canvas.
        kind = kinds[index]
        if kind == 'context':
            return 14, 108 + sum(1 for k in kinds[:index] if k == 'context') * 24
        if kind == 'escape':
            return 210, 167
        fan = sum(1 for k in kinds if k == 'action')
        fan_i = sum(1 for k in kinds[:index] if k == 'action')
        y = 88 if fan == 1 else 26 + fan_i * 126 / max(1, fan - 1)
        return 292, y

    entries, selectors = [], []
    for i, recipe in enumerate(book['recipes'], 1):
        r = {k: escape(str(v)) for k, v in recipe.items() if k != 'options'}
        kinds = [option_kind(o) for o in recipe['options']]
        selectors.append(f'<button type="button" data-recipe-select="recipe-{r["id"]}" aria-controls="recipe-{r["id"]}"><span class="cartridge-number">{i:02}</span>{pixel_glyph(recipe["group"])}<strong>{r["title"]}</strong><span class="cartridge-state" aria-hidden="true">↗</span></button>')
        def option_control(j, option):
            mark = 'UNK' if kinds[j] == 'escape' else f'{j+1:02}'
            arrow = '×' if kinds[j] == 'escape' else '↶' if kinds[j] == 'context' else '↗'
            return f'<span class="choice-static"><small>{mark}</small>{escape(option)}</span><button type="button" data-choice="{j}" data-choice-kind="{kinds[j]}" data-choice-label="{escape(option)}" aria-pressed="false" hidden><small>{mark}</small><span>{escape(option)}</span><i aria-hidden="true">{arrow}</i></button>'
        options = ''.join(f'<li>{option_control(j, option)}</li>' for j, option in enumerate(recipe['options']) if kinds[j] != 'escape')
        abstention = ''.join(option_control(j, option) for j, option in enumerate(recipe['options']) if kinds[j] == 'escape')
        outcomes = ''.join(f'<span data-outcome-state="{key}"><i aria-hidden="true">{mark}</i><b>{key}</b><small>{label}</small></span>' for key, mark, label in (
            ('ok', '↗', '选中已有选项'), ('unknown', '×', '保留判断'), ('refusal', '⊘', 'API 拒答'), ('error', '!', '调用失败')))
        # Static signal field is kept when canvas/JS is unavailable. Candidate labels are HTML.
        wires = ''
        nodes = ''
        for j, kind in enumerate(kinds):
            ex, ey = endpoint(kinds, j)
            if kind == 'context':
                wires += f'<path class="choice-wire" data-choice-wire="{j}" d="M50 90 C26 104 10 {ey-22} {ex} {ey}"/>'
            elif kind == 'escape':
                wires += f'<path class="choice-wire" data-choice-wire="{j}" stroke-dasharray="2 3" d="M66 106 C110 150 160 158 {ex} {ey}"/>'
            else:
                wires += f'<path class="choice-wire" data-choice-wire="{j}" d="M64 90 C140 90 150 {ey} {ex} {ey}"/>'
            nx, ny = ex + 6, ey - 6
            inner = (f'<rect x="{nx+5}" y="{ny+3}" width="2" height="6" fill="#76b39d"/><rect x="{nx+3}" y="{ny+5}" width="6" height="2" fill="#76b39d"/>' if kind == 'context'
                     else ''.join(f'<rect x="{nx+3+d}" y="{ny+3+d}" width="2" height="2" fill="#274a3f"/><rect x="{nx+7-d}" y="{ny+3+d}" width="2" height="2" fill="#274a3f"/>' for d in range(3)) if kind == 'escape'
                     else f'<rect x="{nx+4}" y="{ny+4}" width="4" height="4" fill="#76b39d"/>')
            nodes += f'<rect x="{nx}" y="{ny}" width="12" height="12" fill="#2f5a4e"/><rect x="{nx+2}" y="{ny+2}" width="8" height="8" fill="#0c211e"/>{inner}'
        machine = f'''<figure class="choice-machine"><div class="choice-drawing">
<svg class="pixel-fallback" viewBox="0 0 320 180" aria-hidden="true" shape-rendering="crispEdges"><rect width="320" height="180" fill="#0c211e"/><g fill="none" stroke="#39604f" stroke-width="1">{wires}<path d="M8 90H30"/></g><rect x="49" y="87" width="7" height="7" fill="#76b39d"/><rect x="50" y="88" width="5" height="5" fill="#d9ecae"/><rect x="6" y="86" width="3" height="8" fill="#274a3f"/>{nodes}</svg>
<canvas class="pixel-scene" data-pixel-glyph="{'/'.join(PIXEL_GLYPHS[recipe['group']])}" width="320" height="180" role="img" aria-label="信号场：方形节点可直接点按，也可用旁边的文字按钮试选" title="方形节点可直接点按，与旁边的文字按钮同步" hidden></canvas><span class="machine-coordinate">INPUT → CHOICE → OUTCOME</span></div>
<div class="choice-console"><p class="console-label"><span>试选一个已有选项</span><span>{len(recipe['options']) - kinds.count('escape'):02} CHOICES</span></p><ol class="recipe-options">{options}</ol><div class="choice-abstention"><p>或者，保留判断</p>{abstention}</div></div>
<p class="machine-hint">↖ 图中的方形节点也能点按 · 回环是补材料／交人工，× 是 unknown</p>
<div class="response-preview"><div class="response-heading"><span>RESPONSE / 结果类型</span><small>Choice 任务 · 离线示意 · <a href="docs/method.html#结果状态与输出类型">读结果契约 ↗</a></small></div><div class="outcome-rail" aria-label="四种结果状态">{outcomes}</div>
<p class="choice-readout" role="status" aria-live="polite">尚未试选。选中已有选项与保留判断会产生不同的 outcome。</p>
<dl class="response-values"><div><dt>outcome</dt><dd data-result-outcome>—</dd></div><div><dt>choice</dt><dd data-result-choice>—</dd></div><div><dt>probabilities / confidence</dt><dd>未调用模型 · 无测量值</dd></div></dl>
<div class="response-examples" hidden><span>还可能遇到</span><button type="button" data-outcome-example="refusal" aria-pressed="false">看 API 拒答示例</button><button type="button" data-outcome-example="error" aria-pressed="false">看调用失败示例</button><button type="button" class="preview-reset">清除试选</button></div></div></figure>'''
        label = '已有离线实验' if recipe['status'] == 'implemented-offline' else '接入配方'
        task = json.dumps({key: recipe[key] for key in ('input', 'question', 'options')}, ensure_ascii=False, indent=2)
        entries.append(f'''<details class="recipe" data-recipe-category="{r['group']}" id="recipe-{r['id']}">
<summary><span class="recipe-index">{i:02}</span><span><strong>{r['title']}</strong><small>{r['summary']}</small></span><span class="recipe-toggle" aria-hidden="true">＋</span></summary>
<div class="recipe-body"><div class="recipe-topline"><span>CARTRIDGE / {i:02}</span><span class="recipe-status">{label}</span></div><div class="recipe-brief"><div><h3 class="recipe-name">{r['title']}</h3><p class="recipe-description">{r['summary']}</p></div><div class="recipe-input"><span class="eyebrow">装入什么 / INPUT</span><p>{r['input']}</p></div></div><h4 class="recipe-question">{r['question']}</h4>{machine}
<div class="recipe-connection"><span>接到这个项目</span><a href="{r['project_url']}">{r['project']} ↗</a></div>
<details class="recipe-notes"><summary>拆开配方：第一步、机制与容易踩的坑 <span aria-hidden="true">＋</span></summary><h4>从这里动手</h4><p>{r['first_step']}</p><p>{r['mechanism']}</p><p class="recipe-caution">容易踩坑：{r['failure_mode']}</p><p class="recipe-date">项目证据截点 {r['source_date']} · 创意是本项目提案</p></details>
<div class="recipe-actions"><a href="docs/playbook.html#{r['id']}">完整配方与 API 用法 ↗</a><button type="button" class="recipe-copy" hidden>复制任务 JSON</button></div><pre class="recipe-payload" hidden>{escape(task)}</pre><span class="recipe-copy-status" role="status"></span></div></details>''')
    return f'''<section class="recipe-section" id="playground" aria-labelledby="recipe-title"><div class="playground-heading"><div><p class="eyebrow">01 / 选择也可以很好玩</p><h2 id="recipe-title">把选择，玩出花。</h2><p class="recipe-intro">装入一个问题。拨动一条分支。看看它能通向哪里。</p></div><div class="pixel-sign" data-rise><canvas class="sign-board" data-sign-word="PLAY" data-sign-glyphs="{'/'.join(','.join(v) for v in PIXEL_GLYPHS.values())}" role="img" aria-label="点阵招牌：PLAY 字样与轮播的玩法记号，每屏最多两组" hidden></canvas><span class="sign-static" aria-hidden="true">{pixel_word('PLAY')}</span></div><span class="playground-count">{len(entries):02}<small>玩法卡带 / 6 个方向</small></span></div>
<div class="recipe-tools" data-rise hidden><div class="recipe-groups" role="group" aria-label="按玩法分类">{tabs}</div><label for="recipe-search"><span class="sr-only">找个玩法</span><input id="recipe-search" type="search" placeholder="找个玩法…"></label></div>
<div class="recipe-shelf-label" data-rise><span>选一张卡带 ↓</span><p id="recipe-count" role="status"></p><button type="button" id="pixel-pause" hidden>暂停动态效果</button></div>
<div class="recipe-workbench"><nav class="recipe-selectors" aria-label="选择玩法" data-rise="children" hidden>{''.join(selectors)}</nav><div class="recipe-list" data-rise>{''.join(entries)}<p id="recipe-empty" hidden>没有匹配的玩法。换个词，或选择「全部」。</p></div></div>
<div class="recipe-footer" data-rise><p>手动试选与离线示例 · 浏览器不发送输入，模型结果需接入后另测。</p><a href="docs/playbook.html">全部配方 ↗</a></div></section>'''


def home():
    metadata = json.loads((ROOT/'research/2026-10-08/metadata.json').read_text())
    results = json.loads((ROOT/'research/2026-10-08/reanalysis/sys1_reanalysis.json').read_text())['results']
    evidence = []
    for key, label in (('A_model_router','模型路由'),('B_tool_selection','工具选择'),('F_cardinality_multilingual','多语单选')):
        row, score = results[key], results[key]['jev']
        evidence.append(dict(id=key, label=label, total=row['cases'], correct=score['original_correct'], highTotal=score['high_confidence_n'], highErrors=score['high_confidence_errors']))
    evidence_json = json.dumps(evidence, ensure_ascii=False).replace('<','\\u003c')
    task_buttons = ''.join(f'<button type="button" data-evidence-task="{row["id"]}">{row["id"][0]} / {row["label"]}</button>' for i,row in enumerate(evidence))
    initial = evidence[0]
    source_rows = ''.join(f'<tr><td>{r["label"]}</td><td>{r["correct"]} / {r["total"]}</td><td>{r["highErrors"]} / {r["highTotal"]}</td></tr>' for r in evidence)
    suite = json.loads((ROOT/'experiments/next-action/cases.json').read_text())
    ids = ('relnote-field-zh','missing-doc-placeholder-zh','changelog-breaking-zh')
    cases = [next(c for c in suite['cases'] if c['id']==wanted) for wanted in ids]
    payload = json.dumps(cases,ensure_ascii=False).replace('<','\\u003c')
    task = cases[0]['task']
    def fragment(value): return MarkdownIt('commonmark',{'html':False}).renderInline(value)
    actions = [('inspect_source','核对来源','01'),('compare_contract','比较契约','02'),('read_in_context','结合上下文阅读','03'),('needs_more_context','先补信息','04'),('unknown','没有合适选项','05')]
    buttons = ''.join(f'<button type="button" data-action="{key}"><span>{num}</span>{label}<span class="choice-arrow" aria-hidden="true">↗</span></button>' for key,label,num in actions)
    paths = (
        ('research/2026-10-08/report.html','读清接口的承诺','原生 API、托管路线与开放模型',f'{metadata["research_entities"]} ENTITIES','research'),
        ('docs/method.html','重新认识“可靠”','正确率、覆盖率、校准与错误代价','METHOD NOTES','method'),
        ('docs/integration.html','把判断接入日常','从离线回放走到旁路建议','INTEGRATION','integration'),
    )
    index = ''.join(f'<a class="directory-item" href="{url}">{pixel_glyph(("reading-research", "reliability-lab", "dev-agent")[i])}<span class="directory-id">0{i+1} / {meta}</span><h3>{title}</h3><p>{description}</p><span class="directory-arrow" aria-hidden="true">↗</span></a>' for i,(url,title,description,meta,kind) in enumerate(paths))
    return f'''<section class="cover" aria-labelledby="cover-title">
<div class="cover-heading"><p>独立研究 · 决策模型与可复现实验</p><span>VOL. 01 / OCT 2026</span></div>
<div class="cover-stage">
<h1 id="cover-title" class="sr-only">Decisions Lab</h1>
<div class="cover-type" aria-hidden="true"><span class="type-back">DECISIONS</span><span class="type-front">LAB<span class="cover-asterisk">✳</span></span></div>
<div class="sculpture">{sculpture_fallback()}<canvas id="sculpture-canvas" aria-hidden="true" hidden></canvas></div>
<p class="cover-note"><span>{metadata["repository_index_entries"]} PROJECTS / 05 FIELDS</span>让一个选择，<br>长出许多可能。</p><p class="sculpture-hint" hidden>扫过字母 · 拖拽旋转 · 轻点冲散<br><span>方向键调整 / Home 复位</span></p>
</div>
<div class="cover-bottom"><a href="#playground">向下探索 <span aria-hidden="true">↓</span></a><div class="sculpture-controls" hidden><div role="group" aria-label="粒子形态"><button type="button" data-sculpture-mode="0" aria-pressed="true">编织</button><button type="button" data-sculpture-mode="1" aria-pressed="false">分岔</button><button type="button" data-sculpture-mode="2" aria-pressed="false">环流</button></div><button type="button" id="sculpture-burst">冲散 ↗</button><button type="button" id="sculpture-reset">复位 ↺</button></div><button id="sculpture-pause" type="button" hidden>暂停动态</button></div><p id="sculpture-status" class="sr-only" role="status"></p>
</section>

<section class="fresh-strip"><a href="{html.escape(LATEST_UPDATE_PAGE)}" data-rise><span>{html.escape(LATEST_UPDATE['date'])} / 新观察</span><strong>{html.escape(LATEST_UPDATE['title'])}</strong><span>读增量核查 ↗</span></a></section>
<nav class="lab-wayfinding" aria-label="实验室入口" data-rise="children"><a href="#playground">{pixel_glyph('creative-interactive')}<span>01</span><strong>挑个玩法</strong><small>装入一个问题</small><i aria-hidden="true">↓</i></a><a href="#experiments">{pixel_glyph('reliability-lab')}<span>02</span><strong>拨动实验</strong><small>看看变化怎么发生</small><i aria-hidden="true">↓</i></a><a href="#explore">{pixel_glyph('reading-research')}<span>03</span><strong>带走灵感</strong><small>从这里接到真实项目</small><i aria-hidden="true">↓</i></a></nav>
{recipe_explorer()}
<div class="lab-chapter" id="experiments"><div class="chapter-pixels" aria-hidden="true" data-sign-glyph="reliability-lab">{pixel_glyph("reliability-lab")}</div><p class="eyebrow">02 / 实验进行中</p><h2>小小改动，<br>不同结果。</h2><p>从分布的形状，走到判断的证据，再亲自选一次下一步。</p><nav aria-label="选择实验"><a href="#probability-artifact">A / 调一调概率 ↓</a><a href="#evidence">B / 看一眼错误 ↓</a><a href="#exercise">C / 自己选一次 ↓</a></nav></div>
<section class="field-section" id="probability-artifact" aria-labelledby="field-title">
<div class="field-heading" data-rise><div><p class="eyebrow">EXPERIMENT A / 概率地形</p><h2 id="field-title">概率，长什么样？</h2></div><p>同一组候选，不同的可能性。<br>三座山，三个候选；拖动，改变它们的权重。</p></div>
<div class="field-stage" data-rise><span class="stage-coordinate">FIG. 01 — POSSIBILITY SPACE</span>{field_fallback()}<canvas id="probability-field" role="img" hidden></canvas><div class="field-scale"><span>高</span><i></i><span>低</span><small>概率 / 示意</small></div><div class="field-values"><span><i class="color-a"></i>A <b data-field-value>72.0%</b></span><span><i class="color-b"></i>B <b data-field-value>20.0%</b></span><span><i class="color-c"></i>C <b data-field-value>8.0%</b></span></div></div>
<div class="field-controls" data-rise hidden><div class="field-presets" role="group" aria-label="切换示意分布"><button data-field-preset="0" aria-pressed="true">一边倒</button><button data-field-preset="1" aria-pressed="false">难分高下</button><button data-field-preset="2" aria-pressed="false">双峰</button></div><label class="field-slider" for="field-bias"><span>偏向 A <output id="field-bias-value">72%</output></span><input id="field-bias" type="range" min="0" max="100" value="72"></label><div class="field-stat"><span>maxP</span><b id="field-max">0.72</b></div><div class="field-stat"><span>熵 / bits</span><b id="field-entropy">1.10</b></div><button type="button" id="field-pause">暂停动态</button></div>
<div class="field-foot" data-rise><p>拖动看看：概率改变了形状，却不能独自证明判断正确。</p><span>交互示意 · 无模型调用</span></div><p id="field-summary" class="sr-only" role="status"></p>
</section>
<section class="evidence-section" id="evidence" aria-labelledby="evidence-title"><div class="section-heading" data-rise><h2 id="evidence-title">自信，和正确之间。<span>B / 核对真实的历史记录</span></h2><a href="research/2026-10-08/report.html">阅读完整研究 ↗</a></div><div class="evidence-controls" data-rise hidden><div class="evidence-tasks" role="group" aria-label="历史任务">{task_buttons}</div><div class="evidence-scopes" role="group" aria-label="筛选历史记录"><button data-evidence-scope="all">全部记录</button><button data-evidence-scope="high">只看 maxP ≥ 0.9</button></div></div><div class="evidence-stage" data-rise><div class="evidence-pixels"><svg id="evidence-grid" viewBox="0 0 400 400" role="img" aria-label="历史结果像素图，启用 JavaScript 后可切换"></svg><div class="evidence-legend"><span><i class="color-a"></i>正确</span><span><i class="color-b"></i>错误</span><span><i class="color-muted"></i>筛选外</span></div></div><div class="evidence-reading"><p class="eyebrow">JEV / 2026.10.08 SNAPSHOT</p><p class="evidence-number"><strong id="evidence-accuracy">{initial["correct"]/initial["total"]:.1%}</strong><span>判断正确</span></p><div class="evidence-counts"><p><span id="evidence-correct">{initial["correct"]}</span> / <span id="evidence-total">{initial["total"]}</span><small>选中记录中判断正确</small></p><p><span id="evidence-errors">{initial["total"]-initial["correct"]}</span><small>选中记录中判断错误</small></p></div><p id="evidence-summary" role="status">{initial["label"]}：{initial["correct"]} / {initial["total"]} 判断正确。切换任务，看看同一模型在不同问题上的落差。</p><p class="evidence-note">每格是一条记录的计数；按汇总结果分组排布，位置不代表原始样本顺序。高 maxP 也可能答错。</p></div></div><details class="evidence-source"><summary>展开原始汇总与来源</summary><div class="table-wrap"><table><thead><tr><th>历史任务</th><th>全部记录：正确 / 总数</th><th>高 maxP：错误 / 总数</th></tr></thead><tbody>{source_rows}</tbody></table></div><p>来源：<a href="research/2026-10-08/README.html">sys1-eval 历史复算</a>。任务、样本和条件不同，不是当前模型排名；没有重新调用模型。</p></details><script id="evidence-data" type="application/json">{evidence_json}</script></section>
<section class="decision-exercise" id="exercise" aria-labelledby="exercise-title"><div class="section-heading" data-rise><h2 id="exercise-title">轮到你了。<span>C / 做出你的判断</span></h2><p>三个合成案例 · 选择后查看理由</p></div><div class="exercise-layout"><div class="specimen" data-rise><div class="specimen-top"><span>INPUT / 阅读材料</span><label class="case-selector" hidden>切换用例 <select id="sample-case"><option value="0">01 / 字段更名</option><option value="1">02 / 信息缺失</option><option value="2">03 / 默认值变化</option></select></label></div><p id="sample-document">{fragment(task['document'])}</p><div class="claim"><span>待核对的主张</span><p id="sample-claim">{fragment(task['claim'])}</p></div><p class="sample-source">原创合成输入；来源地址为占位符。</p></div><div class="exercise-actions" data-rise hidden><p class="action-prompt">NEXT ACTION / 下一步，先做什么？</p><div class="choice-list">{buttons}</div><div id="sample-feedback" role="status" aria-live="polite">选择一个动作，查看编辑标签与理由。</div></div><noscript><p>启用 JavaScript 可在本页选择动作，也可以直接<a href="experiments/next-action/README.html">阅读完整实验</a>。</p></noscript></div><div class="exercise-footer" data-rise><p>{len(suite['cases'])} 个原创合成案例，允许多个合理动作。人工标签可讨论。</p><a href="experiments/next-action/README.html">运行完整实验 ↗</a></div><script id="sample-data" type="application/json">{payload}</script></section>
<section class="library-section" id="explore" aria-labelledby="library-title"><div class="section-heading" data-rise><h2 id="library-title">把灵感，接到实现上。<span>03 / TOOLS & READING</span></h2><a href="README.html">关于这个项目 ↗</a></div><div class="library-layout"><div class="project-section"><div class="toolbox-art" aria-hidden="true">{pixel_glyph("dev-agent")}{pixel_glyph("knowledge")}{pixel_glyph("life-choice")}</div><p class="eyebrow">工具箱 / {metadata["repository_index_entries"]} 个历史索引项目</p>{project_atlas()}</div><div class="directory-section"><p class="eyebrow">继续阅读 / 方法与接入</p><div class="directory-grid">{index}</div></div></div></section>
<section class="archive-strip" data-rise><div><p class="eyebrow">A LIVING LAB, DATED EVIDENCE</p><h2>研究持续生长。<br>证据留在它的日期里。</h2><a href="docs/maintenance.html">我们怎样维护这份研究 ↗</a></div><p class="archive-date">2026<span>10.08</span><small>首期调查截点</small></p></section>'''


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
        if rel == 'docs/integration.md':
            # Inline only this owned figure so the reader's theme tokens reach it.
            body, count = re.subn(r'<img src="\.\./site/flow\.svg"[^>]*>', lambda _: (ROOT/'site/flow.svg').read_text(), body)
            if count != 1: raise ValueError('integration figure must have one canonical source')
        if rel == 'docs/projects.md':
            # Progressive enhancement; all research remains readable without JavaScript.
            body = body.replace('</h1>', '</h1><div class="filter" hidden><label for="project-filter">查找项目或机制</label><div class="filter-field"><input id="project-filter" type="search" placeholder="calibration、Laya、SDK…"><button id="filter-clear" type="button">清空</button></div><p id="filter-result" role="status"></p><nav id="filter-matches" aria-label="匹配项目，可跳到表格行" hidden></nav></div>', 1)
        dest = rel.removesuffix('.md')+'.html'
        (output/dest).parent.mkdir(parents=True, exist_ok=True)
        (output/dest).write_text(shell(title, body.replace('<table>', '<div class="table-wrap" tabindex="0" role="region" aria-label="数据表，可横向滚动"><table>').replace('</table>', '</table></div>'), dest, toc), encoding='utf-8')
    (output/'index.html').write_text(shell('决策模型研究与实验', home(), 'index.html'), encoding='utf-8')
    print(f'Built {len(PAGES)+1} pages in _site/ (explicit public allowlist; no network).')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    build(ROOT/'_site')
