// Original generative artwork: a seeded, tilted spiral of square particles.
// Artistic coordinates do not encode model performance or probability.
(function () {
  'use strict';
  const canvas = document.querySelector('#orbit-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  const motion = matchMedia('(prefers-reduced-motion: reduce)');
  const pause = document.querySelector('#orbit-pause');
  let seed = 41;
  function random() { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed / 4294967296; }
  const stars = Array.from({length: 9000}, (_, i) => {
    const r = .23 + Math.pow(random(), .78) * .86;
    const arm = i % 3;
    const angle = arm * Math.PI * 2 / 3 + r * 4.8 + (random()-.5) * (.22 + r*.50);
    return {r, angle, arm, depth:(random()-.5)*.16*(1-r*.55), size:random(), shade:random()};
  });
  const dust = Array.from({length:140}, () => ({x:random(),y:random(),size:random()}));
  let width=0, height=0, time=0, last=0, frame=null, visible=true, paused=motion.matches;
  let pointer={x:0,y:0}, palette;
  function colors() {
    const dark = document.documentElement.dataset.theme === 'dark';
    palette = dark
      ? {arms:['131,174,219','180,155,143','105,165,174'],dust:'150,176,194',ring:'112,151,183',alpha:.80}
      : {arms:['38,76,120','154,95,75','39,105,111'],dust:'73,108,132',ring:'102,135,154',alpha:.73};
  }
  function render() {
    ctx.clearRect(0,0,width,height);
    const compact=width<700;
    const radius=compact ? Math.min(width*.74,height*.57) : Math.min(width*.43,height*.70);
    const cx=width*.5+pointer.x*7, cy=height*.47+pointer.y*5;
    const project=(x,y,z=0) => ({x:cx+(x*.94-y*.25)*radius,y:cy+(x*.22+y*.60+z)*radius});
    for (const dot of dust) {
      ctx.fillStyle=`rgba(${palette.dust},${.12+dot.size*.24})`;
      ctx.fillRect(Math.round(dot.x*width),Math.round(dot.y*height),dot.size>.96?3:1,1);
    }
    // Deliberately incomplete orbit traces, with no decorative UI panels.
    [.96,1.23].forEach((r,index) => {
      ctx.beginPath();
      for(let n=0;n<220;n++) {
        const a=n/219*Math.PI*(index?1.72:1.91)+time*.018+index;
        const p=project(Math.cos(a)*r,Math.sin(a)*r);
        if(n===0) ctx.moveTo(p.x,p.y); else ctx.lineTo(p.x,p.y);
      }
      ctx.strokeStyle=`rgba(${palette.ring},.23)`;ctx.lineWidth=.6;ctx.stroke();
    });
    for(const star of stars) {
      const angle=star.angle+time*.035;
      const p=project(Math.cos(angle)*star.r,Math.sin(angle)*star.r,star.depth);
      const size=(compact?.7:1.0)+star.size*(compact?1.0:1.4);
      const alpha=(.20+star.shade*.80)*palette.alpha;
      ctx.fillStyle=`rgba(${palette.arms[star.arm]},${alpha})`;
      ctx.fillRect(Math.round(p.x),Math.round(p.y),size,size);
    }
    // Three orbiting square nodes make the slow movement perceptible.
    for(let n=0;n<3;n++) {
      const a=n*Math.PI*2/3+time*.08+.3, p=project(Math.cos(a)*1.23,Math.sin(a)*1.23);
      ctx.fillStyle=`rgba(${palette.arms[n]},.9)`;ctx.fillRect(p.x-3,p.y-3,6,6);
      ctx.strokeStyle=`rgba(${palette.arms[n]},.32)`;ctx.strokeRect(p.x-7,p.y-7,14,14);
    }
  }
  function stop() { if(frame!==null) cancelAnimationFrame(frame);frame=null;last=0; }
  function tick(stamp) {
    frame=null;
    if(paused||!visible||document.hidden) return;
    if(!last||stamp-last>=40) { if(last) time+=Math.min(stamp-last,100)/1000;last=stamp;render(); }
    frame=requestAnimationFrame(tick);
  }
  function start() { if(frame===null&&!paused&&visible&&!document.hidden) {last=0;frame=requestAnimationFrame(tick);} }
  function resize() {
    const rect=canvas.getBoundingClientRect();width=rect.width;height=rect.height;
    const dpr=Math.min(devicePixelRatio||1,2);canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);
    ctx.setTransform(dpr,0,0,dpr,0,0);render();
  }
  function pauseLabel() { pause.textContent=paused?'播放粒子运动':'暂停粒子运动';pause.setAttribute('aria-pressed',String(paused)); }
  pause.addEventListener('click',()=>{paused=!paused;pauseLabel();if(paused) stop();else start();});
  motion.addEventListener('change',()=>{if(motion.matches){paused=true;stop();pauseLabel();pointer={x:0,y:0};render();}});
  document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();else start();});
  document.addEventListener('themechange',()=>{colors();render();});
  canvas.addEventListener('pointermove',event=>{
    if(paused||motion.matches)return;
    const rect=canvas.getBoundingClientRect();pointer={x:(event.clientX-rect.left)/width-.5,y:(event.clientY-rect.top)/height-.5};
  });
  canvas.addEventListener('pointerleave',()=>{pointer={x:0,y:0};if(paused)render();});
  colors();canvas.hidden=false;document.querySelector('.orbit-fallback').setAttribute('hidden','');pause.hidden=false;
  pauseLabel();resize();
  new ResizeObserver(resize).observe(canvas);
  new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;if(visible)start();else stop();}).observe(canvas);
  start();
})();
