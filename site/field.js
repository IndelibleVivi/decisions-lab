// Original probability landscape. The field is a mathematical illustration,
// never model inference. Heights follow the displayed distribution.
(function () {
  'use strict';
  const presets = [[0.72, 0.20, 0.08], [0.36, 0.34, 0.30], [0.48, 0.48, 0.04]];
  function entropy(weights) {
    return -weights.reduce((sum, p) => sum + (p > 0 ? p * Math.log2(p) : 0), 0);
  }
  function withFirst(first, ratio) {
    const a = Math.max(0, Math.min(1, first));
    return [a, (1 - a) * ratio, (1 - a) * (1 - ratio)];
  }
  if (typeof module === 'object' && module.exports) module.exports = { entropy, withFirst, presets };
  if (typeof document === 'undefined') return;
  const canvas = document.querySelector('#probability-field');
  if (!canvas) return;
  let context;
  try { context = canvas.getContext('2d'); } catch (_) { return; }
  if (!context) return;
  const slider = document.querySelector('#field-bias');
  const pause = document.querySelector('#field-pause');
  const presetButtons = [...document.querySelectorAll('[data-field-preset]')];
  const media = typeof matchMedia === 'function' ? matchMedia('(prefers-reduced-motion: reduce)') : null;
  const sharedPause = document.querySelector('#pixel-pause');
  let colors;
  function palette() { colors = document.documentElement.dataset.theme === 'dark' ? [[126,168,236],[213,153,137],[120,186,172]] : [[36,79,198],[192,103,88],[47,133,118]]; }
  palette();
  document.addEventListener('themechange', () => { palette(); render(); });
  const peaks = [[-.50, -.30], [.48, -.28], [.04, .53]];
  let weights = [...presets[0]], target = [...weights], ratio = weights[1] / (weights[1] + weights[2]);
  let paused = false, visible = typeof IntersectionObserver !== 'function', frame = null, last = 0, time = 0;
  let width = 0, height = 0, pointer = null;
  const externallyPaused = () => (media && media.matches) || (sharedPause && sharedPause.getAttribute('aria-pressed') === 'true');
  const canRun = () => !paused && !externallyPaused() && visible && !document.hidden && typeof requestAnimationFrame === 'function';
  const dots = [];
  // Back-to-front projection; a fixed lattice keeps identity through changes.
  for (let row = 0; row <= 82; row++) {
    for (let col = 0; col <= 82; col++) {
      const u = (col / 82 - .5) * 2.5, v = (row / 82 - .5) * 2.5;
      if (u*u + v*v > 1.8) continue;
      const fields = peaks.map(([x,y]) => Math.exp(-7 * ((u-x)**2 + (v-y)**2)));
      const density = Math.max(...fields);
      const seed = ((col * 13 + row * 37) % 97) / 97;
      if (density < .018 || seed > Math.min(1, density * 3.2 + .13)) continue;
      dots.push({u,v,fields,seed,density});
    }
  }
  dots.sort((a,b) => a.u+a.v-b.u-b.v);

  function render() {
    context.clearRect(0, 0, width, height);
    const compact = width < 600;
    const spread = compact ? width * .32 : width * .255;
    const elevation = height * .82;
    for (const dot of dots) {
      const contribution = dot.fields.map((value, index) => value * weights[index]);
      const total = contribution.reduce((a,b) => a+b,0);
      const wave = Math.sin(dot.u*7 + dot.v*5 + time*.75) * 1.9 * dot.density;
      const x = width/2 + (dot.u-dot.v) * spread;
      let y = height*.73 + (dot.u+dot.v)*height*.15 - total*elevation + wave;
      // The pointer presses into the terrain; nearby dots lift and brighten.
      let glow = 0;
      if (pointer) {
        const d2 = (x-pointer.x)**2 + (y-pointer.y)**2;
        if (d2 < 16000) { glow = Math.exp(-d2/9000); y -= glow*9; }
      }
      const blend = colors.map((_,channel) => Math.round(contribution.reduce((sum,p,i) => sum + p*colors[i][channel],0) / total));
      context.fillStyle = glow > 0 ? `rgba(${blend.map(c=>Math.round(c+(255-c)*glow*.55)).join(',')},${.55 + dot.density*.45})` : `rgba(${blend.join(',')},${.38 + dot.density*.62})`;
      const size = (compact ? 2.4 : 3.2 + (dot.seed>.86 ? 1.3 : 0)) + glow*1.6;
      context.fillRect(Math.round(x), Math.round(y), size, size);
    }
  }
  function tick(stamp) {
    frame = null;
    if (canRun()) {
      if (!last || stamp-last >= 32) {
        if (last) {
          const dt = Math.min(stamp-last,80)/1000;
          time += dt;
          for (let i = 0; i < 3; i++) weights[i] += (target[i]-weights[i]) * Math.min(1, dt*7);
        }
        last = stamp;
        render();
      }
      frame = requestAnimationFrame(tick);
    }
  }
  function schedule() {
    if (frame === null && canRun() && typeof requestAnimationFrame === 'function') {
      last = 0;
      frame = requestAnimationFrame(tick);
    }
  }
  function stop() {
    if (frame !== null) cancelAnimationFrame(frame);
    frame = null;
    last = 0;
  }
  function resize() {
    const rect = canvas.getBoundingClientRect();
    width = rect.width; height = rect.height;
    const dpr = Math.min(devicePixelRatio || 1, 2);
    canvas.width = Math.round(width*dpr); canvas.height = Math.round(height*dpr);
    context.setTransform(dpr,0,0,dpr,0,0);
    render();
  }
  function showDistribution() {
    const values = target.map(p => (100*p).toFixed(1));
    document.querySelectorAll('[data-field-value]').forEach((node,i) => { node.textContent = values[i] + '%'; });
    document.querySelector('#field-max').textContent = Math.max(...target).toFixed(2);
    document.querySelector('#field-entropy').textContent = entropy(target).toFixed(2);
    document.querySelector('#field-bias-value').textContent = Math.round(target[0]*100) + '%';
    const description = `示意分布：A ${values[0]}%，B ${values[1]}%，C ${values[2]}%。山峰高度随各选项概率变化；不代表真实模型输出。`;
    canvas.setAttribute('aria-label', description);
    document.querySelector('#field-summary').textContent = description;
    // The easing belongs only to the moving illustration. A paused or hidden
    // field must still depict the distribution selected by its working controls.
    if (!canRun()) weights = [...target];
    render();
  }
  presetButtons.forEach((button, index) => button.addEventListener('click', () => {
    target = [...presets[index]];
    ratio = target[1] / (target[1] + target[2]);
    slider.value = String(Math.round(target[0]*100));
    presetButtons.forEach(item => item.setAttribute('aria-pressed', String(item===button)));
    showDistribution();
  }));
  slider.addEventListener('input', () => {
    target = withFirst(Number(slider.value)/100, ratio);
    presetButtons.forEach(item => item.setAttribute('aria-pressed','false'));
    showDistribution();
  });
  function pauseLabel() {
    const still = paused || externallyPaused();
    pause.textContent = still ? '播放动态' : '暂停动态';
    pause.setAttribute('aria-pressed', String(!!still));
    pause.disabled = !!externallyPaused();
  }
  function syncMotion() {
    if (canRun()) schedule();
    else {
      stop(); pointer = null; weights = [...target]; render();
    }
    pauseLabel();
  }
  pause.addEventListener('click', () => {
    if (externallyPaused()) return;
    paused = !paused; syncMotion();
  });
  if (media) media.addEventListener('change', syncMotion);
  document.addEventListener('visibilitychange', syncMotion);
  document.addEventListener('pixelmotionchange', syncMotion);
  canvas.addEventListener('pointermove', event => {
    if (!canRun()) return;
    const rect = canvas.getBoundingClientRect();
    pointer = {x:event.clientX-rect.left,y:event.clientY-rect.top};
    schedule();
  });
  canvas.addEventListener('pointerleave', () => { if (!pointer) return; pointer = null; if (canRun()) schedule(); else render(); });
  canvas.hidden = false;
  document.querySelector('.field-fallback').setAttribute('hidden', '');
  document.querySelector('.field-controls').hidden = false;
  pauseLabel(); showDistribution(); resize();
  if (typeof ResizeObserver === 'function') new ResizeObserver(resize).observe(canvas);
  else window.addEventListener('resize', resize);
  if (typeof IntersectionObserver === 'function') new IntersectionObserver(entries => {
    visible = entries[entries.length - 1].isIntersecting;
    syncMotion();
  }).observe(canvas);
  schedule();
})();
