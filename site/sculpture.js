// Original point-surface sculpture. Geometry is artistic, never a model metric.
(function () {
  'use strict';
  const canvas=document.querySelector('#sculpture-canvas');
  if(!canvas)return;
  const ctx=canvas.getContext('2d');if(!ctx)return;
  const motion=matchMedia('(prefers-reduced-motion: reduce)');
  const pause=document.querySelector('#sculpture-pause');
  const points=[];
  // A tubular trefoil, sampled once. Surface normals carry the lighting.
  for(let i=0;i<420;i++) {
    const t=i/420*Math.PI*2, r=2+Math.cos(3*t), a=2*t;
    const c=[r*Math.cos(a),r*Math.sin(a),Math.sin(3*t)];
    const d=[-3*Math.sin(3*t)*Math.cos(a)-2*r*Math.sin(a),-3*Math.sin(3*t)*Math.sin(a)+2*r*Math.cos(a),3*Math.cos(3*t)];
    const dl=Math.hypot(...d);for(let n=0;n<3;n++)d[n]/=dl;
    const normal=[d[1],-d[0],0],nl=Math.hypot(...normal);for(let n=0;n<3;n++)normal[n]/=nl;
    const bin=[d[1]*normal[2]-d[2]*normal[1],d[2]*normal[0]-d[0]*normal[2],d[0]*normal[1]-d[1]*normal[0]];
    for(let j=0;j<48;j++) {
      const v=j/48*Math.PI*2;
      const n=normal.map((value,k)=>value*Math.cos(v)+bin[k]*Math.sin(v));
      points.push({p:c.map((value,k)=>value+n[k]*.47),n,band:Math.floor(i/84),grain:((i*71+j*137)%101)/100});
    }
  }
  let width=0,height=0,time=0,last=0,frame=null,visible=true,paused=motion.matches,selected=0,dark=false;
  function rotate(p,spin) {
    const a=spin-.44, x=p[0]*Math.cos(a)-p[1]*Math.sin(a),y=p[0]*Math.sin(a)+p[1]*Math.cos(a);
    return [x*.93+p[2]*.367,y*.88-(p[2]*.93-x*.367)*.475,y*.475+(p[2]*.93-x*.367)*.88];
  }
  function render() {
    ctx.clearRect(0,0,width,height);
    const scale=Math.min(width/7.5,height/5.7),pixel=width<600?1.6:2.6;
    const cloud=points.map(dot=>({dot,p:rotate(dot.p,time*.035),n:rotate(dot.n,time*.035)})).sort((a,b)=>a.p[2]-b.p[2]);
    for(const {dot,p,n} of cloud) {
      const light=Math.max(0,n[0]*-.4+n[1]*-.6+n[2]*.7);
      const depth=.83+p[2]*.035;
      const k=light*.75+dot.grain*.25;
      if(dot.grain>.96&&k<.18)continue;
      const base=dark?[57,81,83]:[21,42,43],top=dark?[216,228,197]:[149,166,141];
      if(dot.band===selected&&light>.46) {top[0]=dark?222:190;top[1]=dark?219:109;top[2]=dark?160:78;}
      const rgb=base.map((value,i)=>Math.round(value+(top[i]-value)*k));
      ctx.fillStyle=`rgb(${rgb.join(',')})`;
      const size=pixel*(.72+k*.6);
      ctx.fillRect(Math.round(width*.5+p[0]*scale*depth),Math.round(height*.5+p[1]*scale*depth),size,size);
    }
  }
  function stop(){if(frame!==null)cancelAnimationFrame(frame);frame=null;last=0;}
  function tick(stamp){frame=null;if(paused||!visible||document.hidden)return;if(!last||stamp-last>=66){if(last)time+=Math.min(stamp-last,100)/1000;last=stamp;render();}frame=requestAnimationFrame(tick);}
  function start(){if(frame===null&&!paused&&visible&&!document.hidden){last=0;frame=requestAnimationFrame(tick);}}
  function resize(){const box=canvas.getBoundingClientRect();width=box.width;height=box.height;const dpr=Math.min(devicePixelRatio||1,2);canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);render();}
  function label(){pause.textContent=paused?'播放动态 ↗':'暂停动态 Ⅱ';pause.setAttribute('aria-pressed',String(paused));}
  pause.addEventListener('click',()=>{paused=!paused;label();if(paused)stop();else start();});
  motion.addEventListener('change',()=>{if(motion.matches){paused=true;stop();label();render();}});
  document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();else start();});
  document.addEventListener('themechange',()=>{dark=document.documentElement.dataset.theme==='dark';render();});
  document.addEventListener('atlaschange',event=>{if(Number.isInteger(event.detail.index)&&event.detail.index>=0&&event.detail.index<5){selected=event.detail.index;render();}});
  dark=document.documentElement.dataset.theme==='dark';canvas.hidden=false;document.querySelector('.sculpture-fallback').setAttribute('hidden','');pause.hidden=false;label();resize();
  new ResizeObserver(resize).observe(canvas);
  new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;if(visible)start();else stop();}).observe(canvas);
  start();
})();
