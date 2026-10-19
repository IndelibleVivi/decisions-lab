// A signal field mapping the real response space: action routes fan to square
// nodes, "needs more context / hand to a human" options loop back toward the
// input, and the explicit unknown parks on a dim escape stem. The OUTCOME rail
// (OK / UNK / REF / ERR) follows the same preview state as the HTML readout.
// Refusal/error examples are explicitly synthetic and select no action.
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
  const letters={C:['011','100','100','100','011'],E:['111','100','110','100','111'],F:['111','100','110','100','100'],H:['101','101','111','101','101'],K:['101','110','100','110','101'],N:['101','111','111','101','101'],O:['111','101','101','101','111'],R:['110','101','110','101','101'],T:['111','010','010','010','010'],U:['101','101','101','101','111']};
  // Kinds: 'action' | 'context' (request more info / hand to a human) | 'escape' (explicit unknown).
  function fanIndex(kinds,index){let n=0;for(let i=0;i<index;i++)if(kinds[i]==='action')n++;return n;}
  function fanCount(kinds,count){return count-kinds.reduce((n,k)=>n+(k!=='action'?1:0),0);}
  function contextRank(kinds,index){let n=0;for(let i=0;i<index;i++)if(kinds[i]==='context')n++;return n;}
  function endpoint(kinds,index,count){
    const kind=kinds[index]||'action';
    if(kind==='context')return [14,108+contextRank(kinds,index)*24];
    if(kind==='escape')return [210,167];
    const fan=fanCount(kinds,count),fan_i=fanIndex(kinds,index);
    const y=fan===1?88:26+fan_i*126/(fan-1);
    return [292,y];
  }
  // Route polylines are sampled once so pointAlong/hit-test stay pure geometry.
  function route(index,count,kinds){
    kinds=kinds||[];
    const kind=kinds[index]||'action',end=endpoint(kinds,index,count);
    if(kind==='context'){
      // Loop back toward the input lane: hub → swing left → node at x=14.
      const a=[50,90],c1=[26,104],c2=[10,end[1]-22],b=end,points=[];
      for(let s=0;s<=16;s++){
        const t=s/16,m=1-t;
        points.push([
          m*m*m*a[0]+3*m*m*t*c1[0]+3*m*t*t*c2[0]+t*t*t*b[0],
          m*m*m*a[1]+3*m*m*t*c1[1]+3*m*t*t*c2[1]+t*t*t*b[1]
        ]);
      }
      points[points.length-1]=end.slice();
      return points;
    }
    if(kind==='escape'){
      // unknown is a typed outcome, not an action — it parks on its own lane.
      const a=[66,106],c1=[110,150],c2=[160,158],b=end,points=[];
      for(let s=0;s<=20;s++){
        const t=s/20,m=1-t;
        points.push([
          m*m*m*a[0]+3*m*m*t*c1[0]+3*m*t*t*c2[0]+t*t*t*b[0],
          m*m*m*a[1]+3*m*m*t*c1[1]+3*m*t*t*c2[1]+t*t*t*b[1]
        ]);
      }
      points[points.length-1]=end.slice();
      return points;
    }
    const a=[64,90],c1=[140,90],c2=[150,end[1]],b=end,points=[];
    for(let s=0;s<=22;s++){
      const t=s/22,m=1-t;
      points.push([
        m*m*m*a[0]+3*m*m*t*c1[0]+3*m*t*t*c2[0]+t*t*t*b[0],
        m*m*m*a[1]+3*m*m*t*c1[1]+3*m*t*t*c2[1]+t*t*t*b[1]
      ]);
    }
    points[points.length-1]=end.slice();
    return points;
  }
  function pointAlong(points,progress){
    const lengths=points.slice(1).map((p,i)=>Math.hypot(p[0]-points[i][0],p[1]-points[i][1]));
    let distance=Math.max(0,Math.min(1,progress))*lengths.reduce((a,b)=>a+b,0);
    for(let i=0;i<lengths.length;i++){
      if(distance<=lengths[i]||i===lengths.length-1){if(i===lengths.length-1&&distance+1e-9>=lengths[i])return points.at(-1);const t=lengths[i]?distance/lengths[i]:0;return [points[i][0]+(points[i+1][0]-points[i][0])*t,points[i][1]+(points[i+1][1]-points[i][1])*t];}
      distance-=lengths[i];
    }
    return points[0];
  }
  // Hit targets live on the drawn node: its square sits at endpoint+6,12 wide.
  function hitRoute(x,y,count,kinds){
    kinds=kinds||[];
    for(let i=0;i<count;i++){
      const kind=kinds[i]||'action',end=endpoint(kinds,i,count);
      const hx=Math.abs(x-(end[0]+12)),hy=Math.abs(y-end[1]);
      if(kind==='escape'?hx<=16&&hy<=9:hx<=16&&hy<=11)return i;
    }
    return -1;
  }
  function outcomeOf(kinds,index){
    if(index<0)return null;
    return kinds[index]==='escape'?'unknown':'ok';
  }
  function draw(ctx,state){
    const {time,choice,count,kinds=[],group,glyph,mouse,pulse,hover=-1,outcome=null}=state;
    const C={bg:'#0c211e',star:'#22443a',track:'#39604f',dim:'#274a3f',light:'#d9ecae',soft:'#9dc39b',mint:'#76b39d',dark:'#2f5a4e',orange:'#f3a580',ember:'#c97f55',sweep:'#14332c',loop:'#3e6a5e',pale:'#b8d8c4'};
    const pick=outcome||outcomeOf(kinds,choice);
    const hot=pick==='unknown'?C.pale:pick==='refusal'?C.mint:C.orange;
    function box(x,y,w,h,color){ctx.fillStyle=color;ctx.fillRect(Math.round(x),Math.round(y),w,h);}
    function line(points,color,width=1){ctx.strokeStyle=color;ctx.lineWidth=width;ctx.beginPath();points.forEach((p,i)=>i?ctx.lineTo(Math.round(p[0]),Math.round(p[1])):ctx.moveTo(Math.round(p[0]),Math.round(p[1])));ctx.stroke();}
    function dots(points,color,step=3){for(let i=0;i<points.length;i+=step)box(points[i][0]-1,points[i][1]-1,2,2,color);}
    function sprite(rows,x,y,scale,color){rows.forEach((row,j)=>[...row].forEach((c,i)=>{if(c==='1')box(x+i*scale,y+j*scale,scale,scale,color);}));}
    function number(n,x,y,scale,color){String(n).padStart(2,'0').split('').forEach((c,i)=>sprite(digits[+c].match(/.{3}/g),x+i*4*scale,y,scale,color));}
    function word(text,x,y,scale,color){let cx=x;for(const ch of text){const g=letters[ch];if(g){sprite(g,cx,y,scale,color);cx+=4*scale;}}}
    ctx.imageSmoothingEnabled=false;box(0,0,W,H,C.bg);
    // Sparse stars, blinking on a slow cycle — depth without a dense grid.
    for(let i=0;i<30;i++){
      const x=12+(i*97)%296,y=16+(i*61)%140;
      box(x,y,1,1,(i+Math.floor(time*1.6))%9===0?C.mint:C.star);
    }
    // A faint inspection column drifts across the field.
    const sweep=6+((time*11)%310);
    for(let y=14;y<158;y+=14)box(sweep,y,1,5,C.sweep);
    // Input feed: a thin channel from the left edge into the hub.
    line([[8,90],[30,90]],C.track,2);
    {const p=pointAlong([[8,90],[30,90]],(time*.3)%1);box(p[0]-1,p[1]-1,3,3,C.soft);}
    box(6,86,3,8,C.dim);
    // Routes: S-curves for actions, dotted escape stem, backward loops for context.
    for(let i=0;i<count;i++){
      const kind=kinds[i]||'action';
      const points=route(i,count,kinds),selected=choice===i,end=points.at(-1);
      const hovered=hover===i&&!selected;
      if(kind==='escape'){
        dots(points,selected?hot:hovered?C.mint:'#2b4a40',3);
      }else{
        const color=selected?hot:kind==='context'?C.loop:hovered?C.soft:C.track;
        line(points,color,selected?2.5:1);
      }
      if(selected){
        for(let n=0;n<4;n++){const p=pointAlong(points,(time*.36+n*.22)%1);box(p[0]-2,p[1]-2,4,4,C.light);}
      }else{
        const p=pointAlong(points,(time*.055+i*.21)%1);box(p[0]-1,p[1]-1,2,2,kind==='context'?'#31544a':C.dim);
      }
      // Node: a tappable square. Kind changes its interior mark.
      const nx=end[0]+6,ny=end[1]-6;
      const beat=selected?1:(0.5+0.5*Math.sin(time*1.4+i*1.1));
      const body=selected?hot:hovered?C.mint:kind==='escape'?'#223f37':C.dark;
      box(nx,ny,12,12,body);
      box(nx+2,ny+2,8,8,selected?(pick==='unknown'?'#4d6b58':C.ember):C.bg);
      if(kind==='context'){
        box(nx+5,ny+3,2,6,selected?C.bg:beat>0.7?C.mint:C.dim);
        box(nx+3,ny+5,6,2,selected?C.bg:beat>0.7?C.mint:C.dim);
      }else if(kind==='escape'){
        // 'X' mark: this slot is "none of the actions fit", not an action.
        for(let d=0;d<3;d++){box(nx+3+d,ny+3+d,2,2,selected?C.bg:C.dim);box(nx+7-d,ny+3+d,2,2,selected?C.bg:C.dim);}
      }else{
        box(nx+4,ny+4,4,4,selected?C.bg:(beat>0.7?C.mint:C.dim));
      }
      // Number sprite beside each node; context labels sit right of its left-side node.
      if(kind==='context')number(i+1,nx+16,ny+3,1,selected?hot:C.soft);
      else if(kind==='escape'){word('UNK',end[0]-24,end[1]-3,1,selected?hot:hovered?C.light:'#789a87');}
      else number(i+1,end[0]-9,ny+3,1,selected?hot:hovered?C.light:C.soft);
      // Idle ping: nodes slowly emit a square ripple so the canvas reads as touchable.
      if(!selected){
        const ring=(time*.28+i*.37)%1,r=2+ring*9;
        box(nx-r,ny-r,2,2,ring<.5?C.dim:C.bg);box(nx+12+r,ny-r,2,2,C.dim);box(nx-r,ny+12+r,2,2,C.dim);box(nx+12+r,ny+12+r,2,2,ring<.5?C.dim:C.bg);
      }
      if(selected){
        const a=time*2.2;
        box(nx+6+Math.cos(a)*10,ny+6+Math.sin(a)*10,2,2,hot);
        box(nx+6-Math.cos(a)*10,ny+6-Math.sin(a)*10,2,2,C.light);
      }
      // Hover corners: bracket the node the pointer sits on.
      if(hovered){
        const hx=nx-4,hy=ny-4;
        line([[hx,hy+6],[hx,hy],[hx+6,hy]],C.light);line([[nx+16,ny+10],[nx+16,ny+16],[nx+10,ny+16]],C.light);
      }
    }
    // Hub: a small breathing core with an orbit of motes and a slow beacon ping.
    for(let a=0;a<8;a++){
      const ang=a*Math.PI/4+time*.35,r=13+Math.sin(time*1.7+a)*1.5;
      box(52+Math.cos(ang)*r,90+Math.sin(ang)*r,2,2,a%2?C.dim:C.dark);
    }
    {const ring=(time*.22)%1,r=8+ring*26;for(const [dx,dy] of [[-1,0],[1,0],[0,-1],[0,1]])box(52+dx*r,90+dy*r*.7,2,2,ring<.6?C.sweep:C.bg);}
    box(49,87,7,7,C.mint);box(50,88,5,5,C.light);
    // Signal badge: the group's glyph idles by the hub; a chosen route takes it over.
    if(pick==='refusal'||pick==='error'){
      // A terminal status has no selected route. A barrier replaces the number.
      line([[86,78],[106,98]],hot,2);line([[106,78],[86,98]],hot,2);
      word(pick==='refusal'?'REF':'ERR',90,106,1,hot);
    }else if(choice<0){
      const blink=group==='creative-interactive'&&Math.floor(time*1.1)%6===5;
      sprite(glyph,88,82,2,blink?C.dark:C.mint);
      box(88,102,18,1,C.dim);
    }else if(pick==='unknown'){
      // An unknown pick is not "action N": the badge shows the outcome mark.
      for(let d=0;d<5;d++){box(88+d*3,80+d*3,3,3,C.pale);box(88+(4-d)*3,80+d*3,3,3,C.pale);}
      box(88,99,18,1,C.pale);word('UNK',90,106,1,C.pale);
    }else{
      number(choice+1,88,80,3,hot);
    }
    // Compact visual echo of the fully readable HTML outcome rail.
    word('OUT',236,8,1,C.dim);
    const chips=[['OK','ok'],['UNK','unknown'],['REF','refusal'],['ERR','error']];
    chips.forEach(([label,key],i)=>{
      const x=258+i*15,y=8,lit=pick===key;
      box(x,y,13,8,lit?hot:'#16302a');
      word(label,x+2,y+2,1,lit?C.bg:C.soft);
    });
    // Status cell (bottom right): what a manual pick maps to — a typed outcome,
    // never a fabricated probability or confidence.
    if(pick){
      word('OUT',242,166,1,C.soft);
      box(272,165,40,9,'#16302a');
      word(pick==='unknown'?'UNK':pick==='refusal'?'REF':pick==='error'?'ERR':'OK',282,167,1,hot);
    }else{
      const blink=Math.floor(time*1.2)%2===0;
      word('OUT',242,166,1,C.dim);box(258,167,9,5,'#16302a');
      box(276,167,36,5,'#16302a');if(blink)box(279,168,2,3,C.dim);
    }
    // Footer: eight status cells, one travels slowly.
    const tick=Math.floor(time*2)%8;for(let i=0;i<8;i++)box(16+i*9,170,2,2,i===tick?C.orange:C.dim);
    // A click releases a short square burst from the hub.
    if(pulse>0){for(let i=0;i<14;i++){const angle=i*Math.PI/7,r=14+(1-pulse)*44;box(52+Math.cos(angle)*r,90+Math.sin(angle)*r*.7,2,2,i%2?hot:C.light);}}
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
      const kinds=choices.map(b=>b.dataset.choiceKind==='context'||b.dataset.choiceKind==='escape'?b.dataset.choiceKind:'action');
      const state={time:0,choice:-1,outcome:null,count:choices.length,kinds,group:recipe.dataset.recipeCategory,glyph:(canvas.dataset.pixelGlyph||'').split('/'),mouse:null,pulse:0,hover:-1};
      const scene={recipe,canvas,ctx,choices,state,visible:!win.IntersectionObserver};scenes.push(scene);
      canvas.hidden=false;recipe.querySelector('.pixel-fallback').setAttribute('hidden','');draw(ctx,state);
      const localPoint=e=>{const r=canvas.getBoundingClientRect(),scale=Math.min(r.width/W,r.height/H);return [(e.clientX-r.left-(r.width-W*scale)/2)/scale,(e.clientY-r.top-(r.height-H*scale)/2)/scale];};
      canvas.addEventListener('pointermove',e=>{
        const point=localPoint(e),hit=hitRoute(...point,state.count,state.kinds);
        canvas.style.cursor=hit>=0?'pointer':'crosshair';
        if(state.hover!==hit){state.hover=hit;if(!canRun())render();}
        if(paused||motion.matches)return;
        state.mouse=point;if(!canRun())render();
      });
      canvas.addEventListener('pointerleave',()=>{press=null;state.mouse=null;state.hover=-1;if(!canRun())render();});
      let press=null;
      canvas.addEventListener('pointerdown',e=>{if(e.isPrimary!==false&&e.button===0)press={id:e.pointerId,x:e.clientX,y:e.clientY};});
      canvas.addEventListener('pointercancel',()=>{press=null;});
      canvas.addEventListener('pointerup',e=>{
        if(!press||press.id!==e.pointerId)return;
        const start=press;press=null;if(Math.hypot(e.clientX-start.x,e.clientY-start.y)>8)return;
        const index=hitRoute(...localPoint(e),state.count,state.kinds);if(index>=0)choices[index].click();
      });
      scene.cancel=()=>{press=null;state.mouse=null;state.pulse=0;state.hover=-1;};
    }
    // The shared pause still owns CSS/glyph motion when Canvas 2D is absent.
    let active=null,frame=null,last=null,paused=motion.matches;
    function canRun(){return active&&active.visible&&!paused&&!motion.matches&&!doc.hidden;}
    function render(){if(active)draw(active.ctx,active.state);}
    function stop(){if(frame!==null)win.cancelAnimationFrame(frame);frame=null;last=null;}
    function tick(now){frame=null;if(!canRun())return;const dt=last===null?0:Math.min(.06,(now-last)/1000);last=now;active.state.time+=dt;active.state.pulse=Math.max(0,active.state.pulse-dt*1.7);render();frame=win.requestAnimationFrame(tick);}
    function start(){if(canRun()&&frame===null)frame=win.requestAnimationFrame(tick);}
    function sync(trigger){
      const next=scenes.find(s=>!s.recipe.hidden)||null;
      if(active!==next){if(active)active.cancel();stop();active=next;}
      if(active){
        const selected=active.choices.findIndex(b=>b.getAttribute('aria-pressed')==='true');
        const machine=active.recipe.querySelector('.choice-machine');
        const outcome=machine.dataset.outcome||outcomeOf(active.state.kinds,selected);
        const changed=selected!==active.state.choice||outcome!==active.state.outcome;
        active.state.choice=selected;active.state.outcome=outcome;
        if((changed||trigger)&&!paused&&!motion.matches)active.state.pulse=1;
        // Hovering an option button previews its beam, matching canvas hover.
        const over=active.choices.findIndex(b=>b.matches&&b.matches(':hover'));
        if(over!==active.state.hover){active.state.hover=over;if(!canRun())render();}
        active.canvas.dataset.outcome=outcome||'';
        active.canvas.setAttribute('aria-label',outcome==='refusal'||outcome==='error'
          ?`信号场：${outcome==='refusal'?'API 拒答':'调用失败'}的离线示例，outcome=${outcome}；没有选中任何选项，未发送请求`
          :selected<0?'信号场：尚未手动试选；方形节点可直接点按'
            :outcome==='unknown'
              ?'信号场：手动试选 unknown，保留判断而未选中可执行动作，outcome=unknown；非模型回答'
              :`信号场：手动试选 ${active.choices[selected].dataset.choiceLabel}，路线 ${selected+1}，映射 outcome=ok；非模型回答`);
      }
      render();if(canRun())start();else stop();
    }
    function label(){
      const effective=paused||motion.matches;
      pause.textContent=effective?'播放动态效果':'暂停动态效果';pause.setAttribute('aria-pressed',String(effective));pause.disabled=motion.matches;if(motion.matches)pause.textContent='已减少动态效果';
      doc.documentElement.classList.toggle('is-motion-paused',effective);
      doc.dispatchEvent(new win.CustomEvent('pixelmotionchange',{detail:{paused:effective}}));
    }
    pause.hidden=false;label();
    pause.addEventListener('click',()=>{paused=!paused;label();if(paused){stop();scenes.forEach(s=>s.state.pulse=0);render();}else start();});
    root.addEventListener('click',e=>sync(!!e.target.closest('[data-choice], [data-outcome-example]')));root.addEventListener('input',()=>sync(false));root.addEventListener('pointerover',e=>{if(active&&e.target.closest('[data-choice]'))sync(false);});
    root.addEventListener('pointerout',e=>{if(active&&e.target.closest('[data-choice]')){active.state.hover=-1;if(!canRun())render();}});
    win.addEventListener('hashchange',()=>sync(false));
    motion.addEventListener('change',()=>{if(motion.matches){paused=true;stop();scenes.forEach(s=>s.cancel());}label();render();});
    doc.addEventListener('visibilitychange',()=>{if(doc.hidden){stop();scenes.forEach(s=>s.cancel());}else start();});
    win.addEventListener('blur',()=>{scenes.forEach(s=>s.cancel());render();});
    if(win.IntersectionObserver){
      const observer=new win.IntersectionObserver(entries=>{for(const entry of entries){const scene=scenes.find(s=>s.canvas===entry.target);if(scene){scene.visible=entry.isIntersecting;if(!scene.visible)scene.cancel();}}if(canRun())start();else stop();},{threshold:.05});
      scenes.forEach(s=>observer.observe(s.canvas));
    }
    sync(false);
  }
  return {route,pointAlong,hitRoute,endpoint,outcomeOf,draw,mount};
});
