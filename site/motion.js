// Shared motion layer for the home lab: scroll rise, the LED sign board and
// ambient life for pixel glyphs. Everything is progressive enhancement, fully
// cosmetic, and gated by reduced motion, visibility and the shared pause.
(function (factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (typeof document !== 'undefined') api.mount(document, window);
})(function () {
  'use strict';

  // 5x7 alphabet for the sign board, reused by the static SVG fallback.
  const FONT = {
    A: '01110/10001/10001/11111/10001/10001/10001',
    L: '10000/10000/10000/10000/10000/10000/11111',
    P: '11110/10001/10001/11110/10000/10000/10000',
    Y: '10001/10001/01010/00100/00100/00100/00100',
    '0': '01110/10011/10101/10101/11001/10001/01110',
    '1': '00100/01100/00100/00100/00100/00100/01110',
    '2': '01110/10001/00001/00110/01000/10000/11111',
    '3': '11110/00001/00001/01110/00001/00001/11110',
    '4': '00010/00110/01010/10010/11111/00010/00010',
    '5': '11111/10000/11110/00001/00001/10001/01110',
    '6': '00110/01000/10000/11110/10001/10001/01110',
    '7': '11111/00001/00010/00100/01000/01000/01000',
    '8': '01110/10001/10001/01110/10001/10001/01110',
    '9': '01110/10001/10001/01111/00001/00010/01100',
    '/': '00001/00010/00010/00100/01000/01000/10000'
  };
  function glyphCells(word) {
    // "PLAY" -> [{x,y}] cells on a 1-unit grid, 1 column of air between letters.
    const cells = [];
    let at = 0;
    for (const char of word) {
      const rows = (FONT[char] || '00000/00000/00000/00000/00000/00000/00000').split('/');
      rows.forEach((row, y) => { for (let x = 0; x < row.length; x++) if (row[x] === '1') cells.push({ x: at + x, y }); });
      at += 6;
    }
    return { cells, width: at - 1 };
  }

  function mount(doc, win) {
    const motion = win.matchMedia ? win.matchMedia('(prefers-reduced-motion: reduce)') : null;
    const pause = doc.querySelector('#pixel-pause');
    const motionPaused = () => (motion && motion.matches) || (pause && pause.getAttribute('aria-pressed') === 'true');
    const paused = () => motionPaused() || doc.hidden;
    doc.documentElement.classList.add('has-motion');

    // 1. Scroll rise: one observer, staggered via inline delay. Elements stay
    //    fully readable without JS or with reduced motion (is-in is set directly).
    const rise = [...doc.querySelectorAll('[data-rise]')];
    const target = (el) => el.dataset.rise === 'children' ? [...el.children] : [el];
    for (const el of rise) target(el).forEach((child, i) => { child.classList.add('is-rise'); child.style.transitionDelay = `${Math.min(i, 14) * 55}ms`; });
    const land = (el, still = false) => { for (const child of target(el)) {
      if (still) { child.style.transition = 'none'; child.style.transitionDelay = '0s'; }
      child.classList.add('is-in');
    } };
    let riseObserver = null;
    function landAll() {
      rise.forEach(el => land(el, true));
      if (riseObserver) riseObserver.disconnect();
    }
    if (motionPaused() || !win.IntersectionObserver) landAll();
    else {
      riseObserver = new win.IntersectionObserver(entries => {
        for (const entry of entries) if (entry.isIntersecting) { land(entry.target, !!paused()); riseObserver.unobserve(entry.target); }
      }, { threshold: 0.12, rootMargin: '0px 0px -6% 0px' });
      rise.forEach(el => riseObserver.observe(el));
    }

    // 2. LED sign board for the playground heading. Without a Canvas context,
    //    the authored SVG stays visible; reduced motion uses a still board.
    const board = doc.querySelector('.sign-board');
    let boardState = null;
    if (board && board.dataset.signWord) {
      let ctx = null;
      try { ctx = board.getContext && board.getContext('2d'); } catch (_) { /* Keep the authored SVG. */ }
      if (ctx) {
        board.hidden = false;
        board.width = 460; board.height = 96;
        const staticWord = board.closest('.pixel-sign')?.querySelector('.sign-static');
        if (staticWord) staticWord.setAttribute('hidden', '');
        const word = glyphCells(board.dataset.signWord);
        const glyphs = (board.dataset.signGlyphs || '').split('/').filter(Boolean)
          .map(g => g.split(',').map(row => [...row].map(Number)));
        boardState = { ctx, word, glyphs, time: 0 };
        drawBoard(boardState);
      }
    }
    function drawBoard(s) {
      const { ctx, word, glyphs, time } = s;
      const CW = 7, GAP = 2; // cell width + gutter in canvas px
      const W = ctx.canvas ? ctx.canvas.width : 460, H = ctx.canvas ? ctx.canvas.height : 96;
      ctx.clearRect(0, 0, W, H);
      const C = doc.documentElement.dataset.theme === 'dark'
        ? { dim: '#22313a', on: '#d8ee9a', hot: '#f3a580', mint: '#78baac', grid: '#16222a' }
        : { dim: '#31453e', on: '#dff0b8', hot: '#f3a580', mint: '#71aa95', grid: '#0d231f' };
      const cols = Math.floor(W / (CW + GAP)), rows = Math.floor(H / (CW + GAP));
      const sweep = (Math.sin(time * 0.9) * 0.5 + 0.5) * (cols + 10) - 5; // travelling light column
      const px = c => 3 + c * (CW + GAP), py = r => 3 + r * (CW + GAP);
      for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
        const near = Math.abs(c - sweep) < 1.6;
        ctx.fillStyle = near ? '#274b43' : C.grid;
        ctx.fillRect(px(c), py(r), CW, CW);
      }
      // Word cells, bumped up the board; lit by the sweep and a slow breathe.
      const wx = 2, wy = 2, breathe = 0.55 + 0.45 * Math.sin(time * 1.6);
      for (const cell of word.cells) {
        const c = cell.x + wx, r = cell.y + wy;
        const lit = Math.max(0, 1 - Math.abs(c - sweep) / 2.4);
        ctx.fillStyle = lit > 0.5 ? C.hot : C.on;
        ctx.globalAlpha = 0.75 + 0.25 * Math.min(1, lit + breathe * 0.25);
        ctx.fillRect(px(c), py(r), CW, CW);
      }
      ctx.globalAlpha = 1;
      // The 51×10 grid has room for PLAY and two full 9×9 group marks. Rotate
      // pairs rather than drawing the remaining marks outside the canvas.
      const startCol = wx + word.width + 3, markSize = 9, stride = markSize + 2;
      const slots = Math.max(0, Math.floor((cols - startCol + 2) / stride));
      const pages = slots ? Math.ceil(glyphs.length / slots) : 0;
      const page = pages ? Math.floor(time / 3) % pages : 0;
      const gy = Math.max(0, Math.floor((rows - 1 - markSize) / 2));
      glyphs.slice(page * slots, (page + 1) * slots).forEach((rowsDef, slot) => {
        const i = page * slots + slot, gx = startCol + slot * stride;
        const lift = Math.max(0, Math.sin(time * 1.4 - i * 0.7)) * 1.2;
        rowsDef.forEach((row, y) => row.forEach((v, x) => {
          if (!v) return;
          ctx.fillStyle = i === Math.floor(time * 0.55) % glyphs.length ? C.hot : C.mint;
          ctx.fillRect(px(gx + x), py(gy + y) - lift, CW, CW);
        }));
      });
      // Status strip: a slow marquee of equal cells under everything.
      const run = (time * 14) % (cols + 8);
      for (let c = 0; c < cols; c++) {
        const d = (c - run + cols + 8) % (cols + 8);
        if (d < 6) { ctx.fillStyle = C.dim; ctx.globalAlpha = 1 - d / 6; ctx.fillRect(px(c), py(rows - 1), CW, 2); }
      }
      ctx.globalAlpha = 1;
    }

    // 3. Glyph sparkle: one shared loop lights a wandering cell inside every
    //    visible .pixel-glyph and breathes toolbox tiles.
    const glyphs = [...doc.querySelectorAll('.pixel-glyph')].map(svg => ({
      svg, cells: [...svg.querySelectorAll('rect')], phase: Math.random() * 20, hot: null
    })).filter(g => g.cells.length);
    const glyphVisible = new Map(glyphs.map(g => [g.svg, !win.IntersectionObserver]));
    const fresh = doc.querySelector('.fresh-strip');
    let freshVisible = !win.IntersectionObserver;
    function clearGlyph(g) {
      if (g.hot !== null && g.cells[g.hot]) g.cells[g.hot].removeAttribute('opacity');
      g.hot = null;
    }
    if (win.IntersectionObserver) {
      const watch = new win.IntersectionObserver(entries => {
        for (const entry of entries) {
          glyphVisible.set(entry.target, entry.isIntersecting);
          if (!entry.isIntersecting) {
            const glyph = glyphs.find(g => g.svg === entry.target);
            if (glyph) clearGlyph(glyph);
          }
        }
        sync();
      }, { threshold: 0.1 });
      glyphs.forEach(g => watch.observe(g.svg));
      if (fresh) new win.IntersectionObserver(entries => {
        freshVisible = entries.at(-1).isIntersecting; sync();
      }, { threshold: 0.05 }).observe(fresh);
    }

    let frame = null, last = null, boardVisible = !!boardState && !win.IntersectionObserver;
    const running = () => (boardState && boardVisible) || [...glyphVisible.values()].some(Boolean);
    function stop() {
      if (frame !== null) win.cancelAnimationFrame(frame);
      frame = null; last = null;
    }
    function tick(now) {
      frame = null;
      if (!running() || paused()) { last = null; return; }
      const dt = last === null ? 0 : Math.min(0.06, (now - last) / 1000);
      last = now;
      if (boardState && boardVisible) { boardState.time += dt; drawBoard(boardState); }
      for (const g of glyphs) {
        if (!glyphVisible.get(g.svg)) continue;
        const n = Math.floor((last / 700 + g.phase) % g.cells.length);
        if (g.hot === n) continue;
        if (g.hot !== null && g.cells[g.hot]) g.cells[g.hot].removeAttribute('opacity');
        const cell = g.cells[n];
        if (cell) cell.setAttribute('opacity', '0.38');
        g.hot = n;
      }
      frame = win.requestAnimationFrame(tick);
    }
    function sync() {
      doc.documentElement.classList.toggle('is-motion-hidden', !!doc.hidden);
      if (fresh) fresh.classList.toggle('is-motion-offscreen', !freshVisible);
      for (const g of glyphs) g.svg.style.animationPlayState = !paused() && glyphVisible.get(g.svg) ? 'running' : 'paused';
      if (paused()) {
        if (motionPaused()) landAll();
        glyphs.forEach(clearGlyph); stop();
      } else if (!running()) stop();
      else if (frame === null && win.requestAnimationFrame) frame = win.requestAnimationFrame(tick);
    }
    if (win.IntersectionObserver && boardState) {
      new win.IntersectionObserver(entries => { boardVisible = entries.at(-1).isIntersecting; sync(); }, { threshold: 0.05 }).observe(board);
    }
    doc.addEventListener('visibilitychange', sync);
    doc.addEventListener('pixelmotionchange', sync);
    if (motion) motion.addEventListener('change', () => {
      if (motion.matches && boardState) { boardState.time = 0; drawBoard(boardState); }
      sync();
    });
    doc.addEventListener('themechange', () => { if (boardState) drawBoard(boardState); });
    sync();
  }

  return { glyphCells, FONT, mount };
});
