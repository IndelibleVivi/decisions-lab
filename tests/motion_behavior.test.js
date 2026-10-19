// Deterministic lifecycle checks; real appearance is checked in a browser.
'use strict';
const assert = require('node:assert/strict');
const api = require('../site/motion.js');

// "PLAY" is four letters at 5 columns + 1 gap each: width 23, no negative cells.
const play = api.glyphCells('PLAY');
assert.equal(play.width, 23);
assert.ok(play.cells.length > 40 && play.cells.every(c => c.x >= 0 && c.x < 23 && c.y >= 0 && c.y < 7));
// Unknown characters contribute an empty letter, never a crash.
const odd = api.glyphCells('P~Y');
assert.ok(odd.cells.length > 0);

class Node {
  constructor() { this.listeners = {}; this.attributes = {}; this.dataset = {}; this.style = {}; this.children = []; this.classes = new Set(); this.hidden = false; }
  get classList() { return this; }
  add(...names) { names.forEach(name => this.classes.add(name)); }
  remove(...names) { names.forEach(name => this.classes.delete(name)); }
  toggle(name, force) { const value = force ?? !this.classes.has(name); if (value) this.classes.add(name); else this.classes.delete(name); return value; }
  contains(name) { return this.classes.has(name); }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] ?? null; }
  removeAttribute(name) { delete this.attributes[name]; }
  addEventListener(name, fn) { (this.listeners[name] ??= []).push(fn); }
  fire(type) { for (const fn of this.listeners[type] || []) fn({ type, target: this }); }
  querySelectorAll() { return []; }
}
function setup({ reduce = false, paused = false, observer = true, canvas = true, glyph = true, contextFails = false, raf = true } = {}) {
  const doc = new Node(); doc.documentElement = new Node(); doc.hidden = false;
  const pause = new Node(); pause.setAttribute('aria-pressed', String(paused));
  const rise = new Node(); rise.dataset.rise = 'children'; rise.children = [new Node(), new Node()];
  const mark = new Node(), cells = [new Node(), new Node(), new Node()];
  mark.querySelectorAll = () => cells;
  const fallback = new Node(), sign = new Node(), board = new Node(), fresh = new Node();
  sign.querySelector = () => fallback; board.closest = () => sign;
  board.dataset.signWord = 'PLAY';
  board.dataset.signGlyphs = ['111111111,000000001,100000001,100000001,100000001,100000001,100000001,100000001,111111111',
    '111111111,100000000,100000001,100000001,100000001,100000001,100000001,100000001,111111111',
    '111111111,111111111,100000001,100000001,100000001,100000001,100000001,111111111,111111111',
    '111111111,100000001,111111111,100000001,100000001,100000001,111111111,100000001,111111111',
    '111111111,100000001,100000001,111111111,100000001,111111111,100000001,100000001,111111111',
    '111111111,100000001,100000001,100000001,111111111,100000001,100000001,100000001,111111111'].join('/');
  board.hidden = true;
  let draws = 0, rectangles = [];
  const context = { canvas: board, clearRect() { draws++; rectangles = []; }, fillRect(x,y,width,height) {
    assert.ok([x,y,width,height].every(Number.isFinite), 'sign rectangles are finite');
    assert.ok(x >= 0 && y >= 0 && x + width <= board.width && y + height <= board.height, 'sign drawing stays inside its actual canvas');
    rectangles.push([x,y,width,height]);
  } };
  board.getContext = () => { if (contextFails) throw Error('context denied'); return canvas ? context : null; };
  const selectors = { '#pixel-pause': pause, '.sign-board': canvas || contextFails ? board : null, '.fresh-strip': fresh };
  doc.querySelector = selector => selectors[selector] || null;
  doc.querySelectorAll = selector => selector === '[data-rise]' ? [rise] : selector === '.pixel-glyph' && glyph ? [mark] : selector === '.is-rise' ? rise.children : [];
  const media = new Node(); media.matches = reduce;
  const observed = [], pending = new Map(); let id = 0;
  const win = { matchMedia: () => media,
    requestAnimationFrame: raf ? fn => { pending.set(++id, fn); return id; } : undefined,
    cancelAnimationFrame: next => pending.delete(next),
    IntersectionObserver: observer ? class {
      constructor(fn) { this.fn = fn; this.targets = new Set(); observed.push(this); }
      observe(node) { this.targets.add(node); }
      unobserve(node) { this.targets.delete(node); }
      disconnect() { this.targets.clear(); }
    } : undefined };
  api.mount(doc, win);
  return { doc, win, media, pause, rise, mark, cells, board, fallback, fresh, pending, draws: () => draws, rectangles: () => rectangles.map(rect => [...rect]),
    intersect(node, ...values) { for (const obs of observed) if (obs.targets.has(node)) obs.fn(values.map(isIntersecting => ({ target: node, isIntersecting }))); },
    frame(stamp) { const entry = pending.entries().next().value; assert.ok(entry, 'a scheduled frame exists'); pending.delete(entry[0]); entry[1](stamp); },
    pauseTo(value) { pause.setAttribute('aria-pressed', String(value)); doc.fire('pixelmotionchange'); } };
}

const live = setup();
assert.equal(live.pending.size, 0, 'offscreen components start without an empty loop');
assert.equal(live.mark.style.animationPlayState, 'paused', 'offscreen CSS glyph motion starts paused');
assert.ok(live.fresh.contains('is-motion-offscreen'), 'offscreen decorative strip is paused through its CSS hook');
live.intersect(live.fresh, true);
assert.equal(live.fresh.contains('is-motion-offscreen'), false, 'strip entry releases its CSS pause');
live.intersect(live.board, true); live.intersect(live.board, true);
assert.equal(live.pending.size, 1, 'board entry starts exactly one loop');
live.frame(100); live.frame(150);
assert.ok(live.draws() > 1, 'visible board advances');
live.intersect(live.board, false);
assert.equal(live.pending.size, 0, 'board exit cancels its frame immediately');
const boardDraws = live.draws();
live.intersect(live.mark, true); live.frame(200); live.frame(250);
assert.equal(live.mark.style.animationPlayState, 'running', 'visible glyph releases its CSS animation');
assert.equal(live.draws(), boardDraws, 'offscreen board is not redrawn for a visible glyph');
assert.ok(live.cells.some(cell => cell.getAttribute('opacity') === '0.38'), 'visible glyph sparkles');
live.intersect(live.mark, false);
assert.equal(live.pending.size, 0, 'last glyph exit cancels the shared loop');
assert.ok(live.cells.every(cell => cell.getAttribute('opacity') === null), 'exit restores authored glyph opacity');
live.intersect(live.mark, false, true);
assert.equal(live.pending.size, 1, 'latest observer entry restarts a glyph');
live.pauseTo(true);
assert.equal(live.pending.size, 0, 'shared pause cancels immediately');
assert.ok(live.rise.children.every(child => child.contains('is-in')), 'pause cannot leave unreadable rise targets');
assert.ok(live.cells.every(cell => cell.getAttribute('opacity') === null), 'pause clears cosmetic glyph changes');
live.pauseTo(false);
assert.equal(live.pending.size, 1, 'unpause resumes visible glyphs once');
live.doc.hidden = true; live.doc.fire('visibilitychange');
assert.equal(live.pending.size, 0, 'backgrounding cancels immediately');
assert.ok(live.doc.documentElement.contains('is-motion-hidden'), 'backgrounding provides the CSS ambient pause hook');
assert.equal(live.mark.style.animationPlayState, 'paused', 'backgrounding pauses CSS glyph motion');
live.doc.hidden = false; live.doc.fire('visibilitychange');
assert.equal(live.pending.size, 1, 'foreground resumes once');
live.media.matches = true; live.media.fire('change');
assert.equal(live.pending.size, 0, 'runtime reduced motion cancels the loop');
live.media.matches = false; live.media.fire('change');
assert.equal(live.pending.size, 1, 'runtime motion permission restores a visible loop');
live.pauseTo(true); live.doc.fire('themechange');
assert.equal(live.pending.size, 0, 'theme repaint preserves pause');

const reduced = setup({ reduce: true });
assert.equal(reduced.pending.size, 0, 'initial reduced motion is static');
assert.ok(reduced.rise.children.every(child => child.contains('is-in')), 'initial reduced motion leaves content visible');
const paused = setup({ paused: true });
assert.equal(paused.pending.size, 0, 'initial shared pause is static');
assert.ok(paused.rise.children.every(child => child.contains('is-in')), 'initial pause leaves content visible');
const noIO = setup({ observer: false });
assert.ok(noIO.rise.children.every(child => child.contains('is-in')), 'missing IO preserves readable content');
assert.equal(noIO.pending.size, 1, 'missing IO retains one ambient loop');
const empty = setup({ canvas: false, glyph: false });
assert.equal(empty.pending.size, 0, 'no drawable components means no animation loop');
assert.equal(empty.fallback.getAttribute('hidden'), null, 'missing Canvas preserves static sign');
const denied = setup({ contextFails: true, glyph: false });
assert.equal(denied.pending.size, 0, 'a denied Canvas context is a quiet static fallback');
assert.equal(denied.fallback.getAttribute('hidden'), null, 'denied Canvas keeps the SVG visible');
const noRAF = setup({ observer: false, raf: false });
assert.equal(noRAF.pending.size, 0, 'missing RAF does not break enhancement');
assert.ok(noRAF.rise.children.every(child => child.contains('is-in')), 'static enhancement retains text');

const carousel = setup({ glyph: false });
const markCells = () => carousel.rectangles().filter(([x,y,w,h]) => x >= 255 && w === 7 && h === 7)
  .map(([x,y]) => [Math.round((x-3)/9), Math.round((y-3)/9)]);
const initialMarks = markCells();
carousel.intersect(carousel.board, true);
for (let i = 0; i < 68; i++) carousel.frame(100 + i * 50);
const nextMarks = markCells();
assert.notDeepEqual(initialMarks, nextMarks, 'different pairs of group marks appear without clipping');

console.log('Motion glyph math and lifecycle checks passed (no browser or provider calls).');
