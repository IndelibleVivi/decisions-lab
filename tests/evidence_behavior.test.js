#!/usr/bin/env node
// Dependency-free behavior test for site/evidence.js.
//
// Part 1 drives the pure partition/count function through its CommonJS export
// to assert the four-way outcome split, scope denominators and rejection of
// contradictory input. Part 2 runs the real module inside a minimal DOM/SVG
// shim to assert the rendered grid, pressed states, scope muting and the
// fallback no-op. This is a behavior test, not a pixel/CSS test.
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.resolve(__dirname, '..');
const evidence = require(path.join(ROOT, 'site/evidence.js'));

/* ------------------------------------------------------------- harness */
const results = [];
function check(name, cond, detail) { results.push({ name, ok: !!cond, detail: detail || '' }); }

// Canonical historical aggregates exactly as the template must emit them.
const AGG = {
  A: { id: 'A_model_router', label: '模型路由', total: 400, correct: 200, highTotal: 375, highErrors: 184 },
  B: { id: 'B_tool_selection', label: '工具选择', total: 400, correct: 398, highTotal: 391, highErrors: 0 },
  F: { id: 'F_cardinality_multilingual', label: '高候选数 / 多语单选', total: 200, correct: 162, highTotal: 136, highErrors: 10 },
};

/* ============================== pure partition / count behavior */
function testPartitions() {
  const expected = {
    A: { highCorrect: 191, highWrong: 184, lowCorrect: 9, lowWrong: 16 },
    B: { highCorrect: 391, highWrong: 0, lowCorrect: 7, lowWrong: 2 },
    F: { highCorrect: 126, highWrong: 10, lowCorrect: 36, lowWrong: 28 },
  };
  Object.keys(AGG).forEach((key) => {
    const p = evidence.partition(AGG[key]);
    check('partition ' + key + ': valid', p.ok === true, JSON.stringify(p));
    check('partition ' + key + ': groups match known split',
      p.highCorrect === expected[key].highCorrect && p.highWrong === expected[key].highWrong &&
      p.lowCorrect === expected[key].lowCorrect && p.lowWrong === expected[key].lowWrong,
      JSON.stringify(p));
    check('partition ' + key + ': groups sum to total',
      p.highCorrect + p.highWrong + p.lowCorrect + p.lowWrong === AGG[key].total);
    check('partition ' + key + ': correct = highCorrect + lowCorrect',
      p.correct === p.highCorrect + p.lowCorrect);
    check('partition ' + key + ': highTotal = highCorrect + highWrong',
      p.highTotal === p.highCorrect + p.highWrong);
  });
}

function testMetrics() {
  const a = evidence.partition(AGG.A);
  const allA = evidence.metrics(a, 'all');
  check('metrics A all: denominator is full total', allA.total === 400 && allA.correct === 200);
  check('metrics A all: accuracy is 50.0%', evidence.formatAccuracy(allA.accuracy) === '50.0%',
    evidence.formatAccuracy(allA.accuracy));
  check('metrics A all: errors = total - correct', allA.errors === 200);
  const highA = evidence.metrics(a, 'high');
  check('metrics A high: denominator is high subset only', highA.total === 375 && highA.correct === 191);
  check('metrics A high: errors is the high error count', highA.errors === 184);
  check('metrics A high: accuracy rounds to 50.9%', evidence.formatAccuracy(highA.accuracy) === '50.9%',
    evidence.formatAccuracy(highA.accuracy));

  const b = evidence.partition(AGG.B);
  const highB = evidence.metrics(b, 'high');
  check('metrics B high: perfect subset reads 100.0% and 0 errors',
    highB.correct === 391 && highB.total === 391 && highB.errors === 0 &&
    evidence.formatAccuracy(highB.accuracy) === '100.0%');
  const allB = evidence.metrics(b, 'all');
  check('metrics B all: 99.5%', evidence.formatAccuracy(allB.accuracy) === '99.5%',
    evidence.formatAccuracy(allB.accuracy));

  const f = evidence.partition(AGG.F);
  const highF = evidence.metrics(f, 'high');
  check('metrics F high: 126/136 rounds to 92.6%', highF.total === 136 && highF.correct === 126 &&
    evidence.formatAccuracy(highF.accuracy) === '92.6%', evidence.formatAccuracy(highF.accuracy));
  check('metrics F all: 81.0%', evidence.formatAccuracy(evidence.metrics(f, 'all').accuracy) === '81.0%');
}

function testCellsFor() {
  Object.keys(AGG).forEach((key) => {
    const p = evidence.partition(AGG[key]);
    const cells = evidence.cellsFor(p);
    check('cellsFor ' + key + ': one cell per decision', cells.length === AGG[key].total,
      String(cells.length));
    check('cellsFor ' + key + ': error cells = all wrong',
      cells.filter((c) => c.isError).length === AGG[key].total - AGG[key].correct);
    check('cellsFor ' + key + ': high cells = highTotal',
      cells.filter((c) => c.isHigh).length === AGG[key].highTotal);
    // Deterministic outcome grouping: high correct, high wrong, low correct, low wrong.
    const firstHighWrong = cells.findIndex((c) => c.isHigh && c.isError);
    const firstLowCorrect = cells.findIndex((c) => !c.isHigh && !c.isError);
    if (p.highWrong > 0) {
      check('cellsFor ' + key + ': high-correct block precedes high-error block',
        firstHighWrong === p.highCorrect, String(firstHighWrong));
    }
    if (p.lowCorrect > 0) {
      check('cellsFor ' + key + ': low block follows the high block',
        firstLowCorrect === p.highTotal, String(firstLowCorrect));
    }
  });
}

function testInvalid() {
  const cases = [
    [{ total: 400, correct: 200, highTotal: 401, highErrors: 184 }, 'highTotal > total'],
    [{ total: 400, correct: 401, highTotal: 375, highErrors: 184 }, 'correct > total'],
    [{ total: 400, correct: 200, highTotal: 375, highErrors: 400 }, 'highErrors > highTotal'],
    [{ total: 400, correct: 100, highTotal: 375, highErrors: 10 }, 'highCorrect > correct'],
    [{ total: 400, correct: 200.5, highTotal: 375, highErrors: 184 }, 'non-integer correct'],
    [{ total: 400, correct: -1, highTotal: 375, highErrors: 184 }, 'negative correct'],
    [{ total: 400, correct: 200, highTotal: 375, highErrors: '184' }, 'string highErrors'],
    [{ total: 400, correct: 200, highTotal: 375 }, 'missing highErrors'],
    [{ total: 400, correct: 400, highTotal: 100, highErrors: 1 }, 'high errors exceed all errors'],
    [null, 'null record'],
    [undefined, 'undefined record'],
    [{ total: NaN, correct: 200, highTotal: 375, highErrors: 184 }, 'NaN total'],
    [{ total: Infinity, correct: 200, highTotal: 375, highErrors: 184 }, 'Infinity total'],
  ];
  cases.forEach(([record, why]) => {
    const p = evidence.partition(record);
    check('partition rejects: ' + why, p.ok === false && typeof p.reason === 'string', JSON.stringify(p));
  });
  // The high subset cannot contain more correct answers than the full set.
  const impossible = evidence.partition({ total: 10, correct: 4, highTotal: 10, highErrors: 0 });
  check('partition rejects: high-correct group exceeds all correct', impossible.ok === false, JSON.stringify(impossible));
}

function testPureInput() {
  const original = { total: 400, correct: 200, highTotal: 375, highErrors: 184 };
  const snapshot = JSON.stringify(original);
  evidence.partition(original);
  evidence.metrics(evidence.partition(original), 'all');
  check('partition does not mutate its input', JSON.stringify(original) === snapshot, JSON.stringify(original));
}

/* ============================== minimal DOM / SVG shim for browser path */
class Node {
  constructor(tag, ns) {
    this.tagName = (tag || '').toUpperCase();
    this.namespaceURI = ns || null;
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
  add(...names) { names.forEach((n) => this._classes.add(n)); }
  remove(...names) { names.forEach((n) => this._classes.delete(n)); }
  contains(n) { return this._classes.has(n); }
  setAttribute(k, v) { this.attributes[k] = String(v); if (k === 'class') this._classes = new Set(String(v).split(/\s+/).filter(Boolean)); }
  getAttribute(k) { return k in this.attributes ? this.attributes[k] : null; }
  addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); }
  dispatch(t, e) { (this.listeners[t] || []).forEach((fn) => fn(e || {})); }
  appendChild(c) { c.parentNode = this; this.children.push(c); return c; }
  get textContent() { return this.children.length ? this.children.map((c) => c.textContent).join('') : this._text; }
  set textContent(v) { this._text = String(v); this.children = []; }
  _walk(sel, out) { this.children.forEach((c) => { if (c._matches(sel)) out.push(c); c._walk(sel, out); }); }
  querySelectorAll(sel) { const o = []; this._walk(sel, o); return o; }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
  _matchSimple(token) {
    const m = token.match(/^([.#]?[\w-]*)\[([\w-]+)(?:=["']?([^"'\]]*)["']?)?\]$/);
    if (m) {
      const base = m[1];
      let ok = true;
      if (base.startsWith('.')) ok = this._classes.has(base.slice(1));
      else if (base.startsWith('#')) ok = this.attributes.id === base.slice(1);
      else if (base) ok = this.tagName === base.toUpperCase();
      if (!ok) return false;
      if (m[2] in this.attributes) return m[3] === undefined || String(this.attributes[m[2]]) === m[3];
      return false;
    }
    if (token.startsWith('.')) return this._classes.has(token.slice(1));
    if (token.startsWith('#')) return this.attributes.id === token.slice(1);
    if (token) return this.tagName === token.toUpperCase();
    return true;
  }
  _matches(sel) { const parts = sel.trim().split(/\s+/).filter(Boolean); return this._matchSimple(parts[parts.length - 1]); }
}

function buildDom(aggRecords, { withData = true } = {}) {
  const root = new Node('body');
  const controls = new Node('div');
  controls.setAttribute('class', 'evidence-controls');
  controls.hidden = true;
  const tasks = aggRecords.map((r) => {
    const b = new Node('button');
    b.setAttribute('type', 'button');
    b.setAttribute('data-evidence-task', r.id);
    b.setAttribute('aria-pressed', 'false');
    b.textContent = r.label;
    controls.appendChild(b);
    return b;
  });
  const scopes = ['all', 'high'].map((s) => {
    const b = new Node('button');
    b.setAttribute('type', 'button');
    b.setAttribute('data-evidence-scope', s);
    b.setAttribute('aria-pressed', 'false');
    b.textContent = s;
    controls.appendChild(b);
    return b;
  });
  const grid = new Node('svg');
  grid.setAttribute('id', 'evidence-grid');
  grid.setAttribute('viewBox', '0 0 400 400');
  grid.setAttribute('role', 'img');
  const outputs = {};
  ['correct', 'total', 'accuracy', 'errors', 'summary'].forEach((name) => {
    const p = new Node(name === 'summary' ? 'p' : 'span');
    p.setAttribute('id', 'evidence-' + name);
    root.appendChild(p);
    outputs[name] = p;
  });
  root.appendChild(grid);
  root.appendChild(controls);
  if (withData) {
    const data = new Node('script');
    data.setAttribute('type', 'application/json');
    data.setAttribute('id', 'evidence-data');
    data.textContent = JSON.stringify(aggRecords.map((r) => ({
      id: r.id, label: r.label, total: r.total, correct: r.correct,
      highTotal: r.highTotal, highErrors: r.highErrors,
    })));
    root.appendChild(data);
  }
  return { root, controls, tasks, scopes, grid, outputs };
}

function loadEvidence(dom, extra = {}) {
  const document = {
    querySelector: (s) => dom.root.querySelector(s),
    querySelectorAll: (s) => dom.root.querySelectorAll(s),
    createElement: (t) => new Node(t),
    createElementNS: (ns, t) => new Node(t, ns),
    ...extra,
  };
  const code = fs.readFileSync(path.join(ROOT, 'site/evidence.js'), 'utf8');
  const sandbox = { document, window: {}, console, module: { exports: {} }, Object, Array, String, Number, JSON, Math, isFinite };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox, { filename: 'site/evidence.js' });
  return sandbox;
}

function testBrowserInitial() {
  const dom = buildDom([AGG.A, AGG.B, AGG.F]);
  loadEvidence(dom);
  check('browser: controls revealed once JS runs', dom.controls.hidden === false);
  check('browser: initial task button A is pressed', dom.tasks[0].getAttribute('aria-pressed') === 'true');
  check('browser: other task buttons are not pressed',
    dom.tasks[1].getAttribute('aria-pressed') === 'false' && dom.tasks[2].getAttribute('aria-pressed') === 'false');
  check('browser: scope all pressed, high not',
    dom.scopes[0].getAttribute('aria-pressed') === 'true' && dom.scopes[1].getAttribute('aria-pressed') === 'false');
  const cells = dom.grid.querySelectorAll('.evidence-cell');
  check('browser: A renders 400 cells', cells.length === 400, String(cells.length));
  check('browser: A cells are 14x14 on 18px pitch',
    cells[0].getAttribute('width') === '14' && cells[0].getAttribute('height') === '14' &&
    cells[0].getAttribute('x') === '22' && cells[1].getAttribute('x') === '40' &&
    cells[20].getAttribute('x') === '22' && cells[20].getAttribute('y') === '40');
  check('browser: grid keeps 400x400 viewBox and role=img',
    dom.grid.getAttribute('viewBox') === '0 0 400 400' && dom.grid.getAttribute('role') === 'img');
  check('browser: all-scope numbers are the full task',
    dom.outputs.correct.textContent === '200' && dom.outputs.total.textContent === '400' &&
    dom.outputs.accuracy.textContent === '50.0%' && dom.outputs.errors.textContent === '200');
  check('browser: no cells muted under all scope', cells.every((c) => !c.classList.contains('is-muted')));
  check('browser: summary names the task and the historical nature',
    dom.outputs.summary.textContent.includes('模型路由') &&
    dom.outputs.summary.textContent.includes('200 / 400') &&
    dom.outputs.summary.textContent.includes('历史') &&
    dom.outputs.summary.textContent.includes('不是当前模型排名'),
    dom.outputs.summary.textContent);
  check('browser: svg aria-label summarises counts',
    /正确 200/.test(dom.grid.getAttribute('aria-label')) && /共 400/.test(dom.grid.getAttribute('aria-label')),
    dom.grid.getAttribute('aria-label'));
  // A: highCorrect 191 -> indices 0..190 correct, 191..374 error, 375..383 low correct, 384..399 low error.
  check('browser: cells carry correct/error classes',
    cells[0].classList.contains('is-correct') && cells[190].classList.contains('is-correct') &&
    cells[191].classList.contains('is-error'));
  const lowStart = 191 + 184; // first low cell (A: 375)
  check('browser: low cells are placed after all high cells and start unmuted at all scope',
    lowStart === 375 && cells[lowStart - 1].classList.contains('is-error') &&
    cells[lowStart].classList.contains('is-correct') && cells[lowStart].classList.contains('is-muted') === false);
  return dom;
}

function testBrowserScopeAndTask(dom) {
  const cells = () => dom.grid.querySelectorAll('.evidence-cell');
  dom.scopes[1].dispatch('click'); // high
  check('browser: high scope presses high / unpresses all',
    dom.scopes[1].getAttribute('aria-pressed') === 'true' && dom.scopes[0].getAttribute('aria-pressed') === 'false');
  check('browser: high scope metrics use only the high subset',
    dom.outputs.correct.textContent === '191' && dom.outputs.total.textContent === '375' &&
    dom.outputs.accuracy.textContent === '50.9%' && dom.outputs.errors.textContent === '184');
  check('browser: high scope does not rebuild (same 400 cells)', cells().length === 400);
  check('browser: high scope dims low cells via is-muted',
    cells().slice(191 + 184).every((c) => c.classList.contains('is-muted')));
  check('browser: high scope keeps high cells unmuted',
    cells().slice(0, 375).every((c) => !c.classList.contains('is-muted')));

  dom.scopes[0].dispatch('click'); // back to all
  check('browser: returning to all clears muting', cells().every((c) => !c.classList.contains('is-muted')));

  dom.tasks[2].dispatch('click'); // F
  check('browser: switching task presses F only', dom.tasks[2].getAttribute('aria-pressed') === 'true' &&
    dom.tasks[0].getAttribute('aria-pressed') === 'false');
  check('browser: F rebuilds to 200 cells', cells().length === 200, String(cells().length));
  check('browser: 200-cell grid is centered vertically', cells()[0].getAttribute('y') === '112' && cells()[199].getAttribute('y') === '274');
  check('browser: F all metrics are 162/200 at 81.0%',
    dom.outputs.correct.textContent === '162' && dom.outputs.total.textContent === '200' &&
    dom.outputs.accuracy.textContent === '81.0%');
  dom.scopes[1].dispatch('click');
  check('browser: F high metrics are 126/136 at 92.6%',
    dom.outputs.correct.textContent === '126' && dom.outputs.total.textContent === '136' &&
    dom.outputs.accuracy.textContent === '92.6%' && dom.outputs.errors.textContent === '10');

  dom.tasks[1].dispatch('click'); // B
  check('browser: B renders 400 cells', cells().length === 400);
  check('browser: B high scope is 391/391 at 100.0% with 0 errors',
    dom.outputs.correct.textContent === '391' && dom.outputs.total.textContent === '391' &&
    dom.outputs.accuracy.textContent === '100.0%' && dom.outputs.errors.textContent === '0');
}

function testBrowserRapidSwitching() {
  const dom = buildDom([AGG.A, AGG.B, AGG.F]);
  loadEvidence(dom);
  // Hammer task + scope in many orders, then assert a consistent final state.
  for (let i = 0; i < 25; i++) {
    dom.tasks[i % 3].dispatch('click');
    dom.scopes[i % 2].dispatch('click');
  }
  dom.tasks[0].dispatch('click'); // A
  dom.scopes[0].dispatch('click'); // all
  const cells = dom.grid.querySelectorAll('.evidence-cell');
  check('rapid: final state is A / all with 400 cells', cells.length === 400 &&
    dom.tasks[0].getAttribute('aria-pressed') === 'true' && dom.scopes[0].getAttribute('aria-pressed') === 'true');
  check('rapid: final numbers match A / all', dom.outputs.correct.textContent === '200' &&
    dom.outputs.total.textContent === '400' && dom.outputs.accuracy.textContent === '50.0%');
  check('rapid: no muting left over', cells.every((c) => !c.classList.contains('is-muted')));
  dom.scopes[1].dispatch('click'); // high
  const after = dom.grid.querySelectorAll('.evidence-cell');
  const muted = after.filter((c) => c.classList.contains('is-muted')).length;
  check('rapid: A / high mutes exactly the low cells', muted === 400 - 375, String(muted));
}

function testFallbackNoData() {
  const dom = buildDom([AGG.A], { withData: false });
  let threw = false;
  try { loadEvidence(dom); } catch (err) { threw = true; }
  check('fallback: missing #evidence-data is a quiet no-op', threw === false);
  check('fallback: grid stays empty (template table remains readable)', dom.grid.children.length === 0);
  check('fallback: controls stay hidden', dom.controls.hidden === true);
}

function testFallbackInvalidData() {
  const dom = buildDom([AGG.A]);
  dom.root.querySelector('#evidence-data').textContent = '[{"id":"A","total":400,"correct":200,"highTotal":999,"highErrors":184}]';
  let threw = false;
  try { loadEvidence(dom); } catch (err) { threw = true; }
  check('invalid: contradictory counts do not throw', threw === false);
  check('invalid: no cells are drawn from bad data', dom.grid.children.length === 0);
  check('invalid: metric outputs untouched', dom.outputs.total.textContent === '');

  const dom2 = buildDom([AGG.A]);
  dom2.root.querySelector('#evidence-data').textContent = '{not json';
  let threw2 = false;
  try { loadEvidence(dom2); } catch (err) { threw2 = true; }
  check('invalid: malformed JSON does not throw', threw2 === false);
  check('invalid: malformed JSON draws nothing', dom2.grid.children.length === 0);

  const dom3 = buildDom([AGG.A]);
  dom3.root.querySelector('#evidence-data').textContent = '[]';
  let threw3 = false;
  try { loadEvidence(dom3); } catch (err) { threw3 = true; }
  check('invalid: empty array is a quiet no-op', threw3 === false && dom3.grid.children.length === 0);
}

function testIdentityMapping() {
  const dom = buildDom([AGG.A, AGG.B, AGG.F]);
  dom.root.querySelector('#evidence-data').textContent = JSON.stringify([AGG.F, AGG.B, AGG.A]);
  loadEvidence(dom);
  check('identity: initial F record presses matching F button', dom.tasks[2].getAttribute('aria-pressed') === 'true');
  dom.tasks[0].dispatch('click');
  check('identity: A button uses its id even when records reordered', dom.outputs.correct.textContent === '200' && dom.outputs.total.textContent === '400');
}

function testMotionLifecycle() {
  const dom=buildDom([AGG.A,AGG.B,AGG.F]), handles=[],events={};let observer,changed;
  const reduced={matches:false,addEventListener(_type,fn){changed=fn;}};
  const extra={hidden:false,defaultView:{matchMedia:()=>reduced,IntersectionObserver:class{constructor(fn){observer=fn;}observe(){}}},addEventListener(type,fn){events[type]=fn;},createElementNS(ns,t){const n=new Node(t,ns);n.animate=()=>{const handle={cancelled:false,cancel(){this.cancelled=true;}};handles.push(handle);return handle;};return n;}};
  const sandbox=loadEvidence(dom,extra);
  check('motion: offscreen initial render is static',handles.length===0);
  observer([{isIntersecting:true}]);dom.tasks[1].dispatch('click');
  check('motion: visible change animates the real cells',handles.length===400);
  check('motion: animation never delays real numbers',dom.outputs.correct.textContent==='398');
  dom.scopes[1].dispatch('click');
  check('motion: rapid scope change cancels prior animation',handles.slice(0,400).every(a=>a.cancelled));
  observer([{isIntersecting:false}]);check('motion: leaving viewport cancels every animation',handles.every(a=>a.cancelled));
  observer([{isIntersecting:true}]);dom.tasks[0].dispatch('click');reduced.matches=true;changed();
  check('motion: reduced motion cancels active handles',handles.every(a=>a.cancelled));
  const count=handles.length;dom.tasks[2].dispatch('click');check('motion: reduced motion starts no new animation',handles.length===count);
  reduced.matches=false;dom.tasks[1].dispatch('click');sandbox.document.hidden=true;events.visibilitychange();
  check('motion: background visibility cancels handles',handles.every(a=>a.cancelled));
}

/* ------------------------------------------------------------- run */
testMotionLifecycle();
testIdentityMapping();
testPartitions();
testMetrics();
testCellsFor();
testInvalid();
testPureInput();
const dom = testBrowserInitial();
testBrowserScopeAndTask(dom);
testBrowserRapidSwitching();
testFallbackNoData();
testFallbackInvalidData();

let failed = 0;
for (const r of results) {
  if (!r.ok) failed++;
  console.log(`${r.ok ? 'ok  ' : 'FAIL'} ${r.name}${r.detail ? '  [' + r.detail + ']' : ''}`);
}
console.log(`\n${results.length - failed}/${results.length} behavior checks passed.`);
if (failed) process.exit(1);
