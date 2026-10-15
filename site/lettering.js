// Kinetic lettering is a finite response to the reader's gesture; the real H1 stays intact.
(function () {
  'use strict';
  const stage=document.querySelector('.cover-stage'),type=document.querySelector('.cover-type');
  if(!stage||!type)return;
  const motion=matchMedia('(prefers-reduced-motion: reduce)'),pause=document.querySelector('#sculpture-pause');
  const letters=[];
  for(const word of type.querySelectorAll(':scope > span')){
    for(const node of [...word.childNodes]){
      if(node.nodeType!==Node.TEXT_NODE||!node.textContent.trim())continue;
      const fragment=document.createDocumentFragment();
      for(const char of node.textContent){
        const el=document.createElement('span');el.className='title-letter';el.textContent=char;el.dataset.letter=char;
        fragment.appendChild(el);letters.push({el,x:0,y:0,r:0,vx:0,vy:0,vr:0,tx:0,ty:0,tr:0,cx:0,cy:0,width:0,height:0});
      }
      node.replaceWith(fragment);
    }
  }
  let frame=null,last=null,visible=true,press=null;
  const disabled=()=>motion.matches||document.hidden||!visible||pause?.getAttribute('aria-pressed')==='true';
  function paint(l){l.el.style.transform=`translate(${l.x.toFixed(2)}px,${l.y.toFixed(2)}px) rotate(${l.r.toFixed(2)}deg)`;l.el.style.setProperty('--echo',String(Math.min(.38,(Math.abs(l.y)+Math.abs(l.r))/80)));}
  function stop(){if(frame!==null)cancelAnimationFrame(frame);frame=null;last=null;}
  function reset(){stop();press=null;for(const l of letters){l.x=l.y=l.r=l.vx=l.vy=l.vr=l.tx=l.ty=l.tr=0;paint(l);}}
  function measure(){reset();for(const l of letters){const r=l.el.getBoundingClientRect();l.cx=r.x+r.width/2+window.scrollX;l.cy=r.y+r.height/2+window.scrollY;l.width=r.width;l.height=r.height;}}
  function tick(now){
    frame=null;if(disabled()){reset();return;}
    const dt=last===null?1/60:Math.min(.032,(now-last)/1000);last=now;let moving=false;
    for(const l of letters){
      for(const [p,v,t] of [['x','vx','tx'],['y','vy','ty'],['r','vr','tr']]){l[v]+=(l[t]-l[p])*140*dt;l[v]*=Math.exp(-13*dt);l[p]+=l[v]*dt;if(Math.abs(l[t]-l[p])>.025||Math.abs(l[v])>.05)moving=true;}
      paint(l);
    }
    if(moving)frame=requestAnimationFrame(tick);else last=null;
  }
  function start(){if(!disabled()&&frame===null)frame=requestAnimationFrame(tick);}
  stage.addEventListener('pointermove',e=>{
    if(disabled()||e.pointerType==='touch')return;
    for(const l of letters){const dx=e.pageX-l.cx,dy=e.pageY-l.cy,radius=Math.max(100,l.height*.9),strength=Math.max(0,1-Math.hypot(dx,dy*.8)/radius);l.tx=dx*.09*strength;l.ty=-Math.min(28,l.height*.17)*strength;l.tr=dx/radius*18*strength;}
    if(press&&press.id===e.pointerId&&press.letter){const l=press.letter;l.tx=Math.max(-85,Math.min(85,e.clientX-press.x));l.ty=Math.max(-60,Math.min(60,e.clientY-press.y));l.tr=l.tx*.18;}
    start();
  });
  function release(){for(const l of letters)l.tx=l.ty=l.tr=0;start();}
  stage.addEventListener('pointerleave',release);
  stage.addEventListener('pointerdown',e=>{if(e.isPrimary!==false&&e.button===0)press={id:e.pointerId,x:e.clientX,y:e.clientY,letter:letters.find(l=>Math.abs(e.pageX-l.cx)<l.width/2&&Math.abs(e.pageY-l.cy)<l.height/2)};});
  stage.addEventListener('pointercancel',()=>{press=null;release();});
  stage.addEventListener('lostpointercapture',()=>{press=null;release();});
  stage.addEventListener('pointerup',e=>{
    if(!press||press.id!==e.pointerId)return;
    const old=press;press=null;release();if(disabled()||Math.hypot(e.clientX-old.x,e.clientY-old.y)>8)return;
    const hit=letters.find(l=>Math.abs(e.pageX-l.cx)<l.width/2&&Math.abs(e.pageY-l.cy)<l.height/2);
    if(!hit)return;
    for(const l of letters){const distance=Math.hypot(l.cx-hit.cx,l.cy-hit.cy);l.vy=-270*Math.exp(-distance/220);l.vr=(l.cx-hit.cx)*.15*Math.exp(-distance/220);}
    start();
  });
  window.addEventListener('blur',reset);window.addEventListener('resize',measure);
  document.addEventListener('visibilitychange',()=>{if(document.hidden)reset();});
  motion.addEventListener('change',()=>{if(motion.matches)reset();});
  if(pause)new MutationObserver(()=>{if(disabled())reset();}).observe(pause,{attributes:true,attributeFilter:['aria-pressed']});
  if('IntersectionObserver' in window)new IntersectionObserver(entries=>{visible=entries.at(-1).isIntersecting;if(!visible)reset();}).observe(stage);
  measure();document.fonts?.ready.then(measure);
})();
