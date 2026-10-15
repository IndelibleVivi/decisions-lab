// A deliberately low-resolution signal toy. Routes come from the actual candidate buttons.
// It never predicts a choice, computes a confidence, changes a payload or uses the network.
(function (factory) {
  'use strict';
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  if(typeof document!=='undefined')api.mount(document,window);
})(function () {
  'use strict';
  const W=320,H=180;
  const digits=['111101101101111','010110010010111','111001111100111','111001111001111','101101111001001','111100111001111','111100111101111','111001001001001','111101111101111','111101111001111'];
  function route(index,count){
    const y=count===1?90:28+index*126/(count-1),elbow=195+index*8;
    return [[174,88],[elbow,88],[elbow,y],[302,y]];
  }
  function pointAlong(points,progress){
    const lengths=points.slice(1).map((p,i)=>Math.hypot(p[0]-points[i][0],p[1]-points[i][1]));
    let distance=Math.max(0,Math.min(1,progress))*lengths.reduce((a,b)=>a+b,0);
    for(let i=0;i<lengths.length;i++){
      if(distance<=lengths[i]||i===lengths.length-1){const t=lengths[i]?distance/lengths[i]:0;return [points[i][0]+(points[i+1][0]-points[i][0])*t,points[i][1]+(points[i+1][1]-points[i][1])*t];}
      distance-=lengths[i];
    }
    return points[0];
  }
  function hitRoute(x,y,count){
    if(x<276||x>318)return -1;
    for(let i=0;i<count;i++)if(Math.abs(y-route(i,count).at(-1)[1])<=9)return i;
    return -1;
  }
  function draw(ctx,state){
    const {time,choice,count,group,glyph,mouse,pulse}=state;
    const C={bg:'#102b29',grid:'#21423a',track:'#426557',light:'#cee6a7',soft:'#98bb8e',mint:'#71aa95',dark:'#315d51',orange:'#f3a580'};
    function box(x,y,w,h,color){ctx.fillStyle=color;ctx.fillRect(Math.round(x),Math.round(y),w,h);}
    function line(points,color,width=1){ctx.strokeStyle=color;ctx.lineWidth=width;ctx.beginPath();points.forEach((p,i)=>i?ctx.lineTo(Math.round(p[0]),Math.round(p[1])):ctx.moveTo(Math.round(p[0]),Math.round(p[1])));ctx.stroke();}
    function sprite(rows,x,y,scale,color){rows.forEach((row,j)=>[...row].forEach((c,i)=>{if(c==='1')box(x+i*scale,y+j*scale,scale,scale,color);}));}
    function number(n,x,y,scale,color){String(n).padStart(2,'0').split('').forEach((c,i)=>sprite(digits[+c].match(/.{3}/g),x+i*4*scale,y,scale,color));}
    ctx.imageSmoothingEnabled=false;box(0,0,W,H,C.bg);
    for(let y=17;y<174;y+=8)for(let x=8;x<315;x+=8)box(x,y,1,1,C.grid);
    // A stepped floor and offset machine chassis give the pixels depth without smoothing.
    for(let row=0;row<8;row++)for(let col=0;col<9;col++){
      const x=128+(col-row)*7,y=109+(col+row)*3;
      box(x,y,12,4,(col+row)%3===0?'#2c5143':'#24483e');
    }
    for(let i=0;i<count;i++){
      const points=route(i,count),selected=choice===i,end=points.at(-1);
      line(points,selected?C.orange:C.track,selected?2:1);
      box(end[0]-1,end[1]-5,12,12,selected?C.orange:C.dark);
      box(end[0]+2,end[1]-2,6,6,selected?C.bg:C.mint);
      number(i+1,end[0]-17,end[1]-2,1,selected?C.orange:C.soft);
      if(selected){
        for(let n=0;n<4;n++){
          const progress=((time*.36+n*.22)%1),p=pointAlong(points,progress);
          box(p[0]-2,p[1]-2,4,4,C.light);
        }
      }
    }
    // Input tape: the packet animation is an illustration, never a loading indicator.
    line([[21,104],[73,104],[73,88],[100,88]],C.track,2);
    for(let i=0;i<3;i++){const p=pointAlong([[21,104],[73,104],[73,88],[100,88]],(time*.18+i*.31)%1);box(p[0]-1,p[1]-1,3,3,C.soft);}
    box(18,79,28,36,C.dark);box(16,76,28,34,C.soft);box(20,80,20,3,C.light);
    for(let y=87;y<104;y+=5){box(20,y,3,2,C.bg);box(26,y,12-(y%3)*2,2,C.dark);}
    box(18,110,24,3,C.bg);
    // Main pixel terminal.
    box(108,123,57,6,C.bg);box(116,117,37,8,C.dark);box(112,123,46,5,C.mint);
    box(102,57,66,61,C.dark);box(98,62,78,49,C.dark);box(105,53,62,64,C.soft);box(101,58,70,54,C.soft);
    box(105,53,62,4,C.light);box(101,58,4,49,C.light);box(167,60,4,52,C.mint);box(105,112,62,5,C.mint);
    box(109,63,54,38,C.dark);box(112,66,48,32,C.bg);
    const dx=mouse?Math.round((mouse[0]-136)/90):0,dy=mouse?Math.round((mouse[1]-82)/80):0;
    if(choice<0){
      sprite(glyph,127+Math.max(-3,Math.min(3,dx)),73+Math.max(-2,Math.min(2,dy)),2,C.light);
      if(group==='creative-interactive'&&Math.floor(time*1.1)%6===5)box(128,79,16,2,C.light);
    }else{number(choice+1,126,73,3,C.orange);}
    box(111,106,18,3,C.dark);box(149,105,8,4,choice<0?C.mint:C.orange);box(160,105,3,4,C.light);
    // A small pixel courier gives idle motion a stepped rhythm.
    const step=Math.floor(time*2)%4,botX=57+step*2;
    sprite(['011110','110011','101101','100001','011110','010010'],botX,136,2,C.mint);
    box(botX+4,140,2,2,C.light);box(botX+8,140,2,2,C.light);
    line([[35,152],[44,152],[44,156],[66,156]],C.track);
    const tick=Math.floor(time*4)%16;for(let i=0;i<16;i++)box(18+i*4,165,2,2,i===tick?C.orange:C.grid);
    // A click releases a short square burst. Its final readout was already updated synchronously.
    if(pulse>0){for(let i=0;i<12;i++){const angle=i*Math.PI/6,r=20+(1-pulse)*36;box(137+Math.cos(angle)*r,83+Math.sin(angle)*r*.65,2,2,i%2?C.orange:C.light);}}
    if(mouse){const x=Math.round(mouse[0]/4)*4,y=Math.round(mouse[1]/4)*4;line([[x-4,y-4],[x-4,y-8],[x,y-8]],C.orange);line([[x+4,y+4],[x+4,y+8],[x,y+8]],C.orange);}
  }
  function mount(doc,win){
    const root=doc.querySelector('.recipe-section');if(!root)return;
    const pause=doc.querySelector('#pixel-pause'),motion=win.matchMedia('(prefers-reduced-motion: reduce)');
    const scenes=[];
    for(const recipe of root.querySelectorAll('.recipe')){
      const canvas=recipe.querySelector('.pixel-scene');if(!canvas)continue;
      let ctx;try{ctx=canvas.getContext('2d');}catch(_){continue;}if(!ctx)continue;
      const choices=[...recipe.querySelectorAll('[data-choice]')];
      const state={time:0,choice:-1,count:choices.length,group:recipe.dataset.recipeCategory,glyph:(canvas.dataset.pixelGlyph||'').split('/'),mouse:null,pulse:0};
      const scene={recipe,canvas,ctx,choices,state,visible:!win.IntersectionObserver};scenes.push(scene);
      canvas.hidden=false;recipe.querySelector('.pixel-fallback').setAttribute('hidden','');draw(ctx,state);
      const localPoint=e=>{const r=canvas.getBoundingClientRect(),scale=Math.min(r.width/W,r.height/H);return [(e.clientX-r.left-(r.width-W*scale)/2)/scale,(e.clientY-r.top-(r.height-H*scale)/2)/scale];};
      canvas.addEventListener('pointermove',e=>{const point=localPoint(e);canvas.style.cursor=hitRoute(...point,state.count)>=0?'pointer':'crosshair';if(paused||motion.matches)return;state.mouse=point;if(!canRun())render();});
      canvas.addEventListener('pointerleave',()=>{press=null;state.mouse=null;if(!canRun())render();});
      let press=null;
      canvas.addEventListener('pointerdown',e=>{if(e.isPrimary!==false&&e.button===0)press={id:e.pointerId,x:e.clientX,y:e.clientY};});
      canvas.addEventListener('pointercancel',()=>{press=null;});
      canvas.addEventListener('pointerup',e=>{
        if(!press||press.id!==e.pointerId)return;
        const start=press;press=null;if(Math.hypot(e.clientX-start.x,e.clientY-start.y)>8)return;
        const index=hitRoute(...localPoint(e),state.count);if(index>=0)choices[index].click();
      });
      scene.cancel=()=>{press=null;state.mouse=null;state.pulse=0;};
    }
    if(!scenes.length)return;
    let active=null,frame=null,last=null,paused=motion.matches;
    function canRun(){return active&&active.visible&&!paused&&!motion.matches&&!doc.hidden;}
    function render(){if(active)draw(active.ctx,active.state);}
    function stop(){if(frame!==null)win.cancelAnimationFrame(frame);frame=null;last=null;}
    function tick(now){frame=null;if(!canRun())return;const dt=last===null?0:Math.min(.06,(now-last)/1000);last=now;active.state.time+=dt;active.state.pulse=Math.max(0,active.state.pulse-dt*1.7);render();frame=win.requestAnimationFrame(tick);}
    function start(){if(canRun()&&frame===null)frame=win.requestAnimationFrame(tick);}
    function sync(trigger){
      const next=scenes.find(s=>!s.recipe.hidden)||null;
      if(active!==next){if(active)active.cancel();stop();active=next;}
      if(active){const selected=active.choices.findIndex(b=>b.getAttribute('aria-pressed')==='true');const changed=selected!==active.state.choice;active.state.choice=selected;if((changed||trigger)&&!paused&&!motion.matches)active.state.pulse=1;
        active.canvas.setAttribute('aria-label',selected<0?'像素信号机：尚未手动试选':`像素信号机：手动试选 ${active.choices[selected].dataset.choiceLabel}，路线 ${selected+1}；非模型回答`);
      }
      render();if(canRun())start();else stop();
    }
    function label(){pause.textContent=paused||motion.matches?'播放像素动态':'暂停像素动态';pause.setAttribute('aria-pressed',String(paused||motion.matches));pause.disabled=motion.matches;if(motion.matches)pause.textContent='已减少动态效果';}
    pause.hidden=false;label();
    pause.addEventListener('click',()=>{paused=!paused;label();if(paused){stop();scenes.forEach(s=>s.state.pulse=0);render();}else start();});
    root.addEventListener('click',e=>sync(!!e.target.closest('[data-choice]')));root.addEventListener('input',()=>sync(false));win.addEventListener('hashchange',()=>sync(false));
    motion.addEventListener('change',()=>{if(motion.matches){paused=true;stop();scenes.forEach(s=>s.cancel());}label();render();});
    doc.addEventListener('visibilitychange',()=>{if(doc.hidden){stop();scenes.forEach(s=>s.cancel());}else start();});
    win.addEventListener('blur',()=>{scenes.forEach(s=>s.cancel());render();});
    if(win.IntersectionObserver){
      const observer=new win.IntersectionObserver(entries=>{for(const entry of entries){const scene=scenes.find(s=>s.canvas===entry.target);if(scene){scene.visible=entry.isIntersecting;if(!scene.visible)scene.cancel();}}if(canRun())start();else stop();},{threshold:.05});
      scenes.forEach(s=>observer.observe(s.canvas));
    }
    sync(false);
  }
  return {route,pointAlong,hitRoute,draw,mount};
});
