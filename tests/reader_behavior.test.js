#!/usr/bin/env node
// Dependency-free behavior test for site/reader.js and site/filter.js.
//
// Runs the real modules inside a minimal DOM shim (no browser, no network) so
// the copy / scroll-spy / filter contracts can be asserted in CI. This is a
// behavior test, not a pixel/CSS test: layout, focus rings and the browser's
// clipboard permission prompt are covered by the shared browser acceptance run.
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.resolve(__dirname, '..');

/* ------------------------------------------------------------- mini DOM */
class Node {
  constructor(tag) {
    this.tagName = (tag || '').toUpperCase();
    this.children = [];
    this.parentNode = null;
    this.attributes = {};
    this.style = { props: {}, setProperty: (k, v) => { this.style.props[k] = v; } };
    this.dataset = {};
    this.listeners = {};
    this.hidden = false;
    this._classes = new Set();
    this._text = '';
  }
  get classList() { return this; }
  add() { this._classes.add(arguments[0]); }
  remove() { this._classes.delete(arguments[0]); }
  contains(n) { return this._classes.has(n); }
  get className() { return [...this._classes].join(' '); }
  set className(v) { this._classes = new Set(String(v).split(/\s+/).filter(Boolean)); }
  get id() { return this.attributes.id || ''; }
  set id(v) { this.attributes.id = v; }
  get type() { return this.attributes.type || ''; }
  set type(v) { this.attributes.type = v; }
  get disabled() { return this._disabled || false; }
  set disabled(v) { this._disabled = !!v; }
  get open() { return this._open || false; }
  set open(v) { this._open = !!v; }
  get firstChild() { return this.children[0] || null; }
  get nextSibling() {
    const i = this.parentNode ? this.parentNode.children.indexOf(this) : -1;
    return i >= 0 ? this.parentNode.children[i + 1] || null : null;
  }
  get textContent() {
    if (this.children.length) return this.children.map((c) => c.textContent).join('');
    return this._text;
  }
  set textContent(v) { this._text = String(v); this.children = []; }
  appendChild(c) { c.parentNode = this; this.children.push(c); return c; }
  insertBefore(c, ref) {
    c.parentNode = this;
    const i = ref ? this.children.indexOf(ref) : -1;
    if (i >= 0) this.children.splice(i, 0, c); else this.children.push(c);
    return c;
  }
  setAttribute(k, v) { this.attributes[k] = String(v); }
  getAttribute(k) { return k in this.attributes ? this.attributes[k] : null; }
  removeAttribute(k) { delete this.attributes[k]; }
  addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); }
  dispatch(t, e) { (this.listeners[t] || []).forEach((fn) => fn(e || {})); }
  focus() { this._focused = true; }
  getBoundingClientRect() { return { top: (this._top || 0) - (this._scrollY || 0) }; }
  _walk(sel, out) { this.children.forEach((c) => { if (c._matches(sel)) out.push(c); c._walk(sel, out); }); }
  querySelectorAll(sel) { const o = []; this._walk(sel, o); return o; }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
  _matchSimple(token) {
    // token forms: tag, .class, #id, tag[attr], tag[attr^="v"], .class[attr^="v"]
    const m = token.match(/^([.#]?[\w-]*)\[([\w-]+)([\^$*]?)=?["']?([^"'\]]*)["']?\]?$/);
    if (m) {
      const base = m[1];
      let ok = true;
      if (base.startsWith('.')) ok = this._classes.has(base.slice(1));
      else if (base.startsWith('#')) ok = this.attributes.id === base.slice(1);
      else if (base) ok = this.tagName === base.toUpperCase();
      if (!ok) return false;
      const attr = m[2];
      const has = attr in this.attributes;
      if (!has) return false;
      if (!m[3]) return true; // presence only
      const val = String(this.attributes[attr]);
      if (m[3] === '^') return val.startsWith(m[4]);
      if (m[3] === '$') return val.endsWith(m[4]);
      return val.includes(m[4]);
    }
    if (token.startsWith('.')) return this._classes.has(token.slice(1));
    if (token.startsWith('#')) return this.attributes.id === token.slice(1);
    if (token) return this.tagName === token.toUpperCase();
    return true;
  }
  _matches(sel) {
    const parts = sel.trim().split(/\s+/).filter((p) => p && !p.startsWith(':'));
    const last = parts[parts.length - 1];
    if (!this._matchSimple(last)) return false;
    for (let i = 0; i < parts.length - 1; i++) if (!this._hasAncestor(parts[i])) return false;
    return true;
  }
  _hasAncestor(part) {
    let n = this.parentNode;
    while (n) {
      if (part.startsWith('.')) { if (n._classes.has(part.slice(1))) return true; }
      else if (part.startsWith('#')) { if (n.attributes.id === part.slice(1)) return true; }
      else if (n.tagName === part.toUpperCase()) return true;
      n = n.parentNode;
    }
    return false;
  }
}
const el = (t) => new Node(t);

/* ------------------------------------------------------------- harness */
const results = [];
function check(name, cond, detail) { results.push({ name, ok: !!cond, detail: detail || '' }); }

function loadModule(file, globals) {
  const code = fs.readFileSync(path.join(ROOT, file), 'utf8');
  const sandbox = Object.assign({ console, setTimeout, clearTimeout, decodeURIComponent,
    Object, Array, String, Number, Boolean, Promise }, globals);
  // Share the caller's window object so scrollY mutations are observed.
  sandbox.window = globals.window || {};
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox, { filename: file });
  return sandbox;
}

/* =================================================== reader.js behavior */
function testReaderCopy() {
  const root = el('body');
  const article = el('article');
  const pre = el('pre');
  const code = el('code');
  code.textContent = 'python3 -m decision_lab validate\nline2';
  pre.appendChild(code);
  article.appendChild(pre);
  root.appendChild(article);
  const calls = [];
  loadModule('site/reader.js', {
    document: { querySelectorAll: (s) => root.querySelectorAll(s), querySelector: (s) => root.querySelector(s),
      createElement: (t) => el(t), getElementById: () => null,
      documentElement: { scrollHeight: 1000, style: { setProperty() {} } }, body: root },
    window: { scrollY: 0, innerHeight: 500, addEventListener() {}, requestAnimationFrame(f) { f(); }, getSelection: () => null },
    navigator: { clipboard: { writeText(t) { calls.push(t); return Promise.resolve(); } } },
  });
  const button = pre.querySelector('.copy-code');
  const status = pre.querySelector('.copy-code-status');
  check('reader: copy button added to each pre', !!button);
  check('reader: button is type=button', button && button.type === 'button');
  check('reader: button aria-label states purpose', button && /复制/.test(button.getAttribute('aria-label') || ''));
  check('reader: status element has role=status', status && status.getAttribute('role') === 'status');
  check('reader: original code node is preserved', pre.querySelector('code') === code);
  check('reader: code text untouched', code.textContent === 'python3 -m decision_lab validate\nline2');
  button.dispatch('click');
  return Promise.resolve().then(() => {
    check('reader: copies raw code text', calls[0] === 'python3 -m decision_lab validate\nline2', JSON.stringify(calls[0]));
    check('reader: success shows 已复制', /已复制/.test(status.textContent));
  });
}

function testReaderCopyFailure() {
  const root = el('body');
  const article = el('article');
  const pre = el('pre');
  const code = el('code');
  code.textContent = 'x = 1';
  pre.appendChild(code);
  article.appendChild(pre);
  root.appendChild(article);
  loadModule('site/reader.js', {
    document: { querySelectorAll: (s) => root.querySelectorAll(s), querySelector: (s) => root.querySelector(s),
      createElement: (t) => el(t), getElementById: () => null,
      documentElement: { scrollHeight: 1000, style: { setProperty() {} } }, body: root },
    window: { scrollY: 0, innerHeight: 500, addEventListener() {}, requestAnimationFrame(f) { f(); }, getSelection: () => null },
    navigator: { clipboard: { writeText() { return Promise.reject(new Error('denied')); } } },
  });
  const button = pre.querySelector('.copy-code');
  const status = pre.querySelector('.copy-code-status');
  button.dispatch('click');
  return Promise.resolve().then(() => {
    check('reader: failure shows manual instruction', status.textContent === '请选择代码复制', status.textContent);
    check('reader: failure keeps code selectable (node intact)', pre.querySelector('code') === code);
  });
}

function testReaderScrollSpy() {
  const root = el('body');
  const article = el('article');
  const toc = el('aside');
  toc.className = 'toc';
  const sections = [];
  ['一', '二', '三'].forEach((label, i) => {
    const h2 = el('h2');
    h2.id = 's' + i;
    h2._top = i * 500;
    article.appendChild(h2);
    const link = el('a');
    link.setAttribute('href', '#s' + i);
    link.textContent = label;
    toc.appendChild(link);
    sections.push({ h2, link });
  });
  const mobileToc = el('nav');
  mobileToc.className = 'toc';
  const mobileLinks = sections.map((section) => {
    const link = el('a');
    link.setAttribute('href', section.link.getAttribute('href'));
    mobileToc.appendChild(link);
    return link;
  });
  root.appendChild(mobileToc);
  const progress = el('div');
  progress.className = 'reading-progress';
  root.appendChild(article);
  root.appendChild(toc);
  root.appendChild(progress);
  const listeners = {};
  const win = { scrollY: 0, innerHeight: 600,
    addEventListener(t, fn) { (listeners[t] = listeners[t] || []).push(fn); },
    requestAnimationFrame(f) { f(); }, getSelection: () => null };
  loadModule('site/reader.js', {
    document: { querySelectorAll: (s) => root.querySelectorAll(s), querySelector: (s) => root.querySelector(s),
      createElement: (t) => el(t),
      getElementById: (id) => (sections.find((s) => s.h2.id === id) || {}).h2 || null,
      documentElement: { scrollHeight: 1800, style: { setProperty() {} } }, body: root },
    window: win, navigator: {},
  });
  const fire = () => { sections.forEach((sec) => { sec.h2._scrollY = win.scrollY; }); (listeners.scroll || []).forEach((fn) => fn()); };
  win.scrollY = 0; fire();
  check('reader: first section active at top', sections[0].link.getAttribute('aria-current') === 'location');
  check('reader: only one aria-current at a time', sections.filter((s) => s.link.getAttribute('aria-current')).length === 1);
  win.scrollY = 500 - 126; fire();
  check('reader: mobile anchor selects its own section', sections[1].link.getAttribute('aria-current') === 'location');
  check('reader: both TOCs highlight the same section', mobileLinks[1].getAttribute('aria-current') === 'location' && !mobileLinks[0].getAttribute('aria-current'));
  win.scrollY = 600; fire();
  check('reader: middle section becomes active', sections[1].link.getAttribute('aria-current') === 'location');
  check('reader: prior section cleared', !sections[0].link.getAttribute('aria-current'));
  win.scrollY = 1200; fire();
  check('reader: bottom activates final section', sections[2].link.getAttribute('aria-current') === 'location');
  const pv = parseFloat(progress.style.props['--progress']);
  check('reader: --progress set within 0..1', pv >= 0 && pv <= 1, 'value=' + pv);
}

function testReaderNoOpWithoutTargets() {
  const root = el('body');
  let created = 0;
  loadModule('site/reader.js', {
    document: { querySelectorAll: () => [], querySelector: () => null,
      createElement: (t) => { created++; return el(t); }, getElementById: () => null,
      documentElement: { scrollHeight: 1000, style: { setProperty() {} } }, body: root },
    window: { scrollY: 0, innerHeight: 500, addEventListener() {}, requestAnimationFrame(f) { f(); }, getSelection: () => null },
    navigator: {},
  });
  check('reader: quiet no-op when no targets exist', created === 0);
  return true;
}

/* =================================================== filter.js behavior */
function buildProjectsDom(withClear) {
  const root = el('body');
  const article = el('article');
  const panel = el('div');
  panel.className = 'filter';
  panel.hidden = true;
  const input = el('input');
  input.id = 'project-filter';
  input.value = '';
  const status = el('p');
  status.id = 'filter-result';
  panel.appendChild(input);
  panel.appendChild(status);
  const matches = el('nav'); matches.id = 'filter-matches';
  panel.appendChild(matches);
  let clear = null;
  if (withClear) { clear = el('button'); clear.id = 'filter-clear'; panel.appendChild(clear); }
  article.appendChild(panel);

  const headingA = el('h2'); headingA.textContent = '调用契约与 SDK';
  const boundaryA = el('p'); boundaryA.textContent = '局限：兼容接口不保证语义相同。';
  const wrapA = el('div'); wrapA.className = 'table-wrap';
  const tbodyA = el('tbody');
  const rowsA = [];
  [['typesafe-sdk-python', '同步/异步'], ['openai-python', 'Decisions 请求类型']].forEach(([a, b]) => {
    const tr = el('tr'); const t1 = el('td'); t1.textContent = a; const t2 = el('td'); t2.textContent = b;
    tr.appendChild(t1); tr.appendChild(t2); tbodyA.appendChild(tr); rowsA.push(tr);
  });
  wrapA.appendChild(tbodyA);

  const headingB = el('h2'); headingB.textContent = '继续追踪的线索';
  const boundaryB = el('p'); boundaryB.textContent = '以下的线索证据深度不足。';
  const wrapB = el('div'); wrapB.className = 'table-wrap';
  const tbodyB = el('tbody');
  const rowsB = [];
  [['laya', '校准 confidence'], ['kev', 'pointer head']].forEach(([a, b]) => {
    const tr = el('tr'); const t1 = el('td'); t1.textContent = a; const t2 = el('td'); t2.textContent = b;
    tr.appendChild(t1); tr.appendChild(t2); tbodyB.appendChild(tr); rowsB.push(tr);
  });
  wrapB.appendChild(tbodyB);

  [headingA, wrapA, boundaryA, headingB, wrapB, boundaryB].forEach((n) => article.appendChild(n));
  root.appendChild(article);
  return { root, panel, input, status, matches, clear, wrapA, wrapB, rowsA, rowsB, headingA, headingB, boundaryA, boundaryB };
}

function loadFilter(dom) {
  const document = {
    querySelector: (s) => dom.root.querySelector(s),
    querySelectorAll: (s) => dom.root.querySelectorAll(s),
    createElement: (t) => el(t),
    getElementById: (id) => dom.root.querySelectorAll('#' + id)[0] || null,
    documentElement: { scrollHeight: 1000, style: { setProperty() {} } }, body: dom.root,
  };
  const code = fs.readFileSync(path.join(ROOT, 'site/filter.js'), 'utf8');
  const sandbox = { document, window: {}, navigator: {}, console, setTimeout, clearTimeout, Object, Array, String };
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox, { filename: 'site/filter.js' });
}

function testFilter() {
  const dom = buildProjectsDom(true);
  loadFilter(dom);
  check('filter: panel revealed once JS runs', dom.panel.hidden === false);
  check('filter: initial status shows total', /4/.test(dom.status.textContent), dom.status.textContent);
  check('filter: clear disabled with empty query', dom.clear.disabled === true);
  check('filter: all rows visible initially', dom.rowsA.every((r) => !r.hidden) && dom.rowsB.every((r) => !r.hidden));
  check('filter: no group hidden initially', dom.wrapA.hidden === false && dom.wrapB.hidden === false);

  dom.input.value = 'typesafe'; dom.input.dispatch('input');
  check('filter: matching row stays visible', dom.rowsA[0].hidden === false);
  check('filter: non-matching row hidden', dom.rowsA[1].hidden === true);
  check('filter: group B (no match) wrapper hidden', dom.wrapB.hidden === true);
  check('filter: group B heading still visible', dom.headingB.hidden === false);
  check('filter: group B boundary text still visible', dom.boundaryB.hidden === false);
  check('filter: clear enabled with query', dom.clear.disabled === false);
  check('filter: status reports match count', /1\s*\/\s*4/.test(dom.status.textContent), dom.status.textContent);

  check('filter: jump link names the matching project', dom.matches.children.length === 1 && dom.matches.children[0].textContent.includes('typesafe-sdk-python'));
  check('filter: jump targets the matching row', dom.matches.children[0].getAttribute('href') === '#' + dom.rowsA[0].id);
  dom.input.value = 'zzz-no-such-project'; dom.input.dispatch('input');
  check('filter: no-match hides both tables', dom.wrapA.hidden === true && dom.wrapB.hidden === true);
  check('filter: headings survive no-match', dom.headingA.hidden === false && dom.headingB.hidden === false);
  check('filter: boundary text survives no-match', dom.boundaryA.hidden === false && dom.boundaryB.hidden === false);
  check('filter: no-match status explains limitation', /未命中/.test(dom.status.textContent) && /局限/.test(dom.status.textContent), dom.status.textContent);

  check('filter: no-match clears previous jump links', dom.matches.hidden && dom.matches.children.length === 0);
  dom.clear.dispatch('click');
  check('filter: clear empties input', dom.input.value === '');
  check('filter: clear restores all rows', dom.rowsA.every((r) => !r.hidden) && dom.rowsB.every((r) => !r.hidden));
  check('filter: clear restores both tables', dom.wrapA.hidden === false && dom.wrapB.hidden === false);
  check('filter: clear returns focus to search', dom.input._focused === true);
  check('filter: clear disabled again after clearing', dom.clear.disabled === true);
}

function testFilterNoInput() {
  const root = el('body');
  const article = el('article');
  const tbody = el('tbody');
  const tr = el('tr'); tr.textContent = 'ordinary row';
  tbody.appendChild(tr);
  article.appendChild(tbody);
  root.appendChild(article);
  const document = { querySelector: (s) => root.querySelector(s), querySelectorAll: (s) => root.querySelectorAll(s),
    createElement: (t) => el(t), getElementById: () => null,
    documentElement: { scrollHeight: 1000, style: { setProperty() {} } }, body: root };
  const code = fs.readFileSync(path.join(ROOT, 'site/filter.js'), 'utf8');
  const sandbox = { document, window: {}, navigator: {}, console, setTimeout, clearTimeout, Object, Array, String };
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox, { filename: 'site/filter.js' });
  check('filter: no #project-filter leaves ordinary rows untouched', tr.hidden === false);
}

async function main() {
  await testReaderCopy();
  await testReaderCopyFailure();
  testReaderScrollSpy();
  testReaderNoOpWithoutTargets();
  testFilter();
  testFilterNoInput();
  await new Promise((r) => setTimeout(r, 10));

  let failed = 0;
  for (const r of results) {
    if (!r.ok) failed++;
    console.log(`${r.ok ? 'ok  ' : 'FAIL'} ${r.name}${r.detail ? '  [' + r.detail + ']' : ''}`);
  }
  console.log(`\n${results.length - failed}/${results.length} behavior checks passed.`);
  if (failed) process.exit(1);
}

main();
