#!/usr/bin/env node
// Dependency-free behavior test for site/atlas.js (catalog category selector).
//
// Runs the real module inside a minimal DOM shim (no browser, no network) so
// the selection / aria / fallback contracts can be asserted in CI.
// This is a behavior test, not a pixel/CSS test: focus behavior, real keyboard
// activation and the decorative canvas are covered by the browser run.
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
  get textContent() {
    if (this.children.length) return this.children.map((c) => c.textContent).join('');
    return this._text;
  }
  set textContent(v) { this._text = String(v); this.children = []; }
  appendChild(c) { c.parentNode = this; this.children.push(c); return c; }
  setAttribute(k, v) { this.attributes[k] = String(v); }
  getAttribute(k) { return k in this.attributes ? this.attributes[k] : null; }
  addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); }
  dispatch(t, e) { (this.listeners[t] || []).forEach((fn) => fn(e || {})); }
  _walk(sel, out) { this.children.forEach((c) => { if (c._matches(sel)) out.push(c); c._walk(sel, out); }); }
  querySelectorAll(sel) { const o = []; this._walk(sel, o); return o; }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
  _matchSimple(token) {
    // supports: tag, .class, #id, [attr], [attr="v"], tag[attr="v"], .class[attr]
    const m = token.match(/^([.#]?[\w-]*)\[([\w-]+)(?:=["']?([^"'\]]*)["']?)?\]$/);
    if (m) {
      const base = m[1];
      let ok = true;
      if (base.startsWith('.')) ok = this._classes.has(base.slice(1));
      else if (base.startsWith('#')) ok = this.attributes.id === base.slice(1);
      else if (base) ok = this.tagName === base.toUpperCase();
      if (!ok) return false;
      const attr = m[2];
      if (!(attr in this.attributes)) return false;
      if (m[3] === undefined) return true;
      return String(this.attributes[attr]) === m[3];
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

function loadAtlas(globals) {
  const code = fs.readFileSync(path.join(ROOT, 'site/atlas.js'), 'utf8');
  const sandbox = Object.assign({ console, Error }, globals);
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox, { filename: 'site/atlas.js' });
  return sandbox;
}

// Loads the module without a global document so it does not auto-mount; the
// caller drives the exported mount()/select() handle explicitly. A module
// object is provided so the factory's API lands in module.exports.
function loadAtlasApi() {
  const code = fs.readFileSync(path.join(ROOT, 'site/atlas.js'), 'utf8');
  const sandbox = { console, Error, module: { exports: {} } };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox, { filename: 'site/atlas.js' });
  return sandbox.module.exports;
}

/* ---------------------------------------------------- DOM construction */
// Builds #project-atlas with the given groups. `groups` entries are
// {id,label}; the first panel is left visible (static markup), the others are
// hidden. A button is created per group; a panel per group holding a link.
function buildAtlas(groups) {
  const root = el('body');
  const atlas = el('div'); atlas.id = 'project-atlas';
  const controls = el('div'); controls.className = 'atlas-controls'; controls.hidden = true;
  const buttonWrap = el('div');
  const status = el('p'); status.id = 'atlas-status';
  const buttons = {};
  const panels = {};
  const links = {};
  groups.forEach((g, i) => {
    const button = el('button'); button.type = 'button';
    button.setAttribute('data-atlas-group', g.id);
    button.setAttribute('data-label', g.label);
    button.textContent = g.label;
    buttons[g.id] = button;
    buttonWrap.appendChild(button);

    const panel = el('section');
    panel.setAttribute('data-atlas-panel', g.id);
    panel.hidden = i !== 0;
    panels[g.id] = panel;
    const link = el('a');
    link.setAttribute('href', 'projects.html#' + g.id);
    link.textContent = g.label;
    panel.appendChild(link);
    links[g.id] = link;
    atlas.appendChild(panel);
  });
  controls.appendChild(buttonWrap);
  atlas.appendChild(controls);
  atlas.appendChild(status);
  root.appendChild(atlas);

  const document = {
    querySelector: (s) => root.querySelector(s),
    querySelectorAll: (s) => root.querySelectorAll(s),
    getElementById: (id) => root.querySelectorAll('#' + id)[0] || null,
    createElement: (t) => el(t),
  };
  return { root, atlas, controls, status, buttons, panels, links, document };
}

const GROUPS = [
  { id: 'sdk', label: '调用契约与 SDK' },
  { id: 'models', label: '开放模型与决策头' },
  { id: 'eval', label: '评测与运行时' },
];

/* ============================================================== checks */
function testHappyPath() {
  const dom = buildAtlas(GROUPS);
  loadAtlas({ document: dom.document });

  check('atlas: controls revealed once JS runs', dom.controls.hidden === false);
  check('atlas: first group pressed, others not',
    dom.buttons.sdk.getAttribute('aria-pressed') === 'true' &&
    dom.buttons.models.getAttribute('aria-pressed') === 'false' &&
    dom.buttons.eval.getAttribute('aria-pressed') === 'false');
  check('atlas: first panel visible, others hidden',
    dom.panels.sdk.hidden === false && dom.panels.models.hidden === true && dom.panels.eval.hidden === true);
  check('atlas: status announces first label',
    dom.status.textContent === GROUPS[0].label, dom.status.textContent);

  dom.buttons.models.dispatch('click');
  check('atlas: selecting a second group shows only its panel',
    dom.panels.models.hidden === false && dom.panels.sdk.hidden === true && dom.panels.eval.hidden === true);
  check('atlas: selecting a second group moves aria-pressed',
    dom.buttons.models.getAttribute('aria-pressed') === 'true' &&
    dom.buttons.sdk.getAttribute('aria-pressed') === 'false' &&
    dom.buttons.eval.getAttribute('aria-pressed') === 'false');
  check('atlas: status follows the selected group',
    dom.status.textContent === GROUPS[1].label, dom.status.textContent);

  dom.buttons.eval.dispatch('click');
  check('atlas: third group selection isolates its panel',
    dom.panels.eval.hidden === false && dom.panels.sdk.hidden === true && dom.panels.models.hidden === true);
  check('atlas: status names the third group', dom.status.textContent === GROUPS[2].label);
  dom.buttons.eval.dispatch('click');

  check('atlas: panels keep real links into projects',
    dom.links.sdk.getAttribute('href') === 'projects.html#sdk' &&
    dom.links.models.getAttribute('href') === 'projects.html#models' &&
    dom.links.eval.getAttribute('href') === 'projects.html#eval');
  check('atlas: all controls are type=button',
    dom.buttons.sdk.type === 'button' && dom.buttons.models.type === 'button' && dom.buttons.eval.type === 'button');
}

function testIdempotentReselect() {
  const dom = buildAtlas(GROUPS);
  loadAtlas({ document: dom.document });

  dom.buttons.models.dispatch('click');
  const before = dom.panels.models.hidden;
  dom.buttons.models.dispatch('click');
  dom.buttons.models.dispatch('click');
  check('atlas: repeated selection of same group stays selected',
    dom.panels.models.hidden === before && dom.panels.models.hidden === false &&
    dom.buttons.models.getAttribute('aria-pressed') === 'true');
  check('atlas: repeated selection does not disturb other panels',
    dom.panels.sdk.hidden === true && dom.panels.eval.hidden === true);
  check('atlas: status still names the same group', dom.status.textContent === GROUPS[1].label);
}

// Selecting by identity, not by order: a handler bound to a group id must keep
// targeting that group even when the button order is scrambled in the DOM.
function testGroupIdsNotOrder() {
  const dom = buildAtlas(GROUPS);
  // move the eval button before sdk to prove handlers use ids, not indices
  const wrap = dom.controls.querySelector('.atlas-controls') || dom.controls.children[0];
  const evalBtn = dom.buttons.eval;
  wrap.children = [evalBtn, dom.buttons.sdk, dom.buttons.models];
  loadAtlas({ document: dom.document });

  check('atlas: initial group is still the first DOM panel id, not button order',
    dom.panels.sdk.hidden === false && dom.panels.eval.hidden === true);
  dom.buttons.eval.dispatch('click');
  check('atlas: reordered button selects its own panel by id',
    dom.panels.eval.hidden === false && dom.panels.sdk.hidden === true && dom.panels.models.hidden === true);
  check('atlas: reordered button presses only itself',
    dom.buttons.eval.getAttribute('aria-pressed') === 'true' &&
    dom.buttons.sdk.getAttribute('aria-pressed') === 'false');
}

function testMissingPanel() {
  const dom = buildAtlas(GROUPS);
  // drop the models panel: control without a panel -> controls stay hidden
  const panel = dom.panels.models;
  panel.parentNode.children = panel.parentNode.children.filter((c) => c !== panel);
  loadAtlas({ document: dom.document });

  check('atlas: missing panel keeps controls hidden', dom.controls.hidden === true);
  check('atlas: missing panel leaves static panels untouched',
    dom.panels.sdk.hidden === false && dom.panels.eval.hidden === true);
  check('atlas: missing panel presses no control',
    dom.buttons.sdk.getAttribute('aria-pressed') === null &&
    dom.buttons.models.getAttribute('aria-pressed') === null);
  check('atlas: missing panel changes no status text',
    dom.status.textContent === '', JSON.stringify(dom.status.textContent));
  dom.buttons.models.dispatch('click');
  check('atlas: click on a control in malformed DOM does nothing',
    dom.panels.sdk.hidden === false);
}

function testOrphanPanel() {
  const dom = buildAtlas(GROUPS);
  // add a panel with no button -> count mismatch -> hidden fallback
  const orphan = el('section');
  orphan.setAttribute('data-atlas-panel', 'ghost');
  orphan.hidden = true;
  dom.atlas.appendChild(orphan);
  loadAtlas({ document: dom.document });
  check('atlas: orphan panel keeps controls hidden', dom.controls.hidden === true);
  check('atlas: orphan panel leaves static panels untouched',
    dom.panels.sdk.hidden === false && dom.panels.models.hidden === true);
}

function testDuplicateGroup() {
  const dom = buildAtlas(GROUPS);
  const dup = el('section');
  dup.setAttribute('data-atlas-panel', 'sdk'); // two panels for one control
  dup.hidden = true;
  dom.atlas.appendChild(dup);
  loadAtlas({ document: dom.document });
  check('atlas: duplicate panel id keeps controls hidden', dom.controls.hidden === true);
}

function testAbsentRoot() {
  const root = el('body');
  const status = el('p'); status.id = 'atlas-status';
  root.appendChild(status);
  const document = {
    querySelector: (s) => root.querySelector(s),
    querySelectorAll: (s) => root.querySelectorAll(s),
    getElementById: (id) => root.querySelectorAll('#' + id)[0] || null,
    createElement: (t) => el(t),
    dispatchEvent: () => true,
  };
  loadAtlas({ document });
  check('atlas: absent root mounts nothing and stays silent', status.textContent === '');
}

function testNoStatusStillWorks() {
  const dom = buildAtlas(GROUPS);
  const status = dom.status;
  status.parentNode.children = status.parentNode.children.filter((c) => c !== status);
  loadAtlas({ document: dom.document });
  check('atlas: without #atlas-status selection still works',
    dom.controls.hidden === false && dom.panels.sdk.hidden === false);
  dom.buttons.eval.dispatch('click');
  check('atlas: without status the panel still swaps', dom.panels.eval.hidden === false);
}

// The exported mount() handle exposes select(); an unknown group id must be a
// no-op so a bad call can never hide every panel or disturb the current selection.
function testSelectUnknownId() {
  const dom = buildAtlas(GROUPS);
  const sandbox = loadAtlasApi();
  const handle = sandbox.mount(dom.document);
  check('atlas: mount returns a select handle', handle && typeof handle.select === 'function');
  const result = handle.select('no-such-group');
  check('atlas: select(unknown) returns without change', result == null);
  check('atlas: select(unknown) leaves the current panel visible',
    dom.panels.sdk.hidden === false && dom.panels.models.hidden === true && dom.panels.eval.hidden === true);
  check('atlas: select(unknown) presses only the current control',
    dom.buttons.sdk.getAttribute('aria-pressed') === 'true' &&
    dom.buttons.models.getAttribute('aria-pressed') === 'false');
}

// A missing .atlas-controls has nothing to reveal, so the selector must bail
// without touching the statically rendered panels.
function testMissingControls() {
  const dom = buildAtlas(GROUPS);
  const controls = dom.controls;
  controls.parentNode.children = controls.parentNode.children.filter((c) => c !== controls);
  loadAtlas({ document: dom.document });
  check('atlas: missing .atlas-controls bails', dom.panels.sdk.hidden === false);
  check('atlas: missing controls leaves every static panel as rendered',
    dom.panels.sdk.hidden === false && dom.panels.models.hidden === true && dom.panels.eval.hidden === true);
  check('atlas: missing controls presses no button',
    dom.buttons.sdk.getAttribute('aria-pressed') === null);
}

/* ---------------------------------------------------------------- main */
const tests = [testHappyPath, testIdempotentReselect, testGroupIdsNotOrder,
  testMissingPanel, testOrphanPanel, testDuplicateGroup, testAbsentRoot, testNoStatusStillWorks,
  testSelectUnknownId, testMissingControls];
tests.forEach((t) => {
  try { t(); } catch (err) { check(t.name + ' threw', false, err && err.message); }
});

let failed = 0;
for (const r of results) {
  if (!r.ok) failed++;
  console.log(`${r.ok ? 'ok  ' : 'FAIL'} ${r.name}${r.detail ? '  [' + r.detail + ']' : ''}`);
}
console.log(`\n${results.length - failed}/${results.length} atlas behavior checks passed.`);
if (failed) process.exit(1);
