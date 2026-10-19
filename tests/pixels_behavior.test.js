'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs');
const api=require('../site/pixels.js');
const catalog=JSON.parse(fs.readFileSync('catalog/recipes.json','utf8'));
const kindOf=o=>o==='unknown'?'escape':(/需要|需补|人工|材料不足|送人复核|先补/.test(o)?'context':'action');
for(const recipe of catalog.recipes){
 const kinds=recipe.options.map(kindOf),count=recipe.options.length;
 for(let i=0;i<count;i++){
  const path=api.route(i,count,kinds),end=path.at(-1);
  assert.deepEqual(api.pointAlong(path,0),path[0]);assert.deepEqual(api.pointAlong(path,1),end);
  const target=kinds[i]==='context'?[end[0]+12,end[1]]:[end[0]+12,end[1]];
  assert.equal(api.hitRoute(target[0],target[1],count,kinds),i,'every actual option has its own hit target');
  assert.ok(path.every(([x,y])=>x>=0&&x<=320&&y>=0&&y<=180),`${recipe.id} route ${i} stays on canvas`);
 }
 // unknown is distinct from every executable/domain choice, including context.
 for(let i=0;i<count;i++){
  assert.equal(api.outcomeOf(kinds,i),kinds[i]==='escape'?'unknown':'ok',`${recipe.id} option ${i} outcome`);
 }
}
assert.equal(api.hitRoute(100,88,6),-1,'machine body never invents a candidate');
class Element {
 constructor(){this.events={};this.attrs={};this.style={};this.hidden=false;this.dataset={};this.nodes={};this.lists={};this.classList={toggle(){}};}
 addEventListener(k,fn){(this.events[k]??=[]).push(fn);}fire(k,e={}){for(const fn of this.events[k]||[])fn(e);}
 querySelector(k){return this.nodes[k]||null;}querySelectorAll(k){return this.lists[k]||[];}
 getAttribute(k){return this.attrs[k]??null;}setAttribute(k,v){this.attrs[k]=String(v);}
}
function setup({reduced=false,noCanvas=false}={}){
 const root=new Element(),pause=new Element(),doc=new Element(),win=new Element(),motion=new Element();motion.matches=reduced;
 doc.documentElement=new Element();win.CustomEvent=class{constructor(type,options){this.type=type;this.detail=options.detail;}};doc.dispatchEvent=e=>doc.fire(e.type,e);
 const frames=new Map();let id=0,observer;
 win.matchMedia=()=>motion;win.requestAnimationFrame=fn=>{frames.set(++id,fn);return id;};win.cancelAnimationFrame=n=>frames.delete(n);
 win.IntersectionObserver=class{constructor(fn){observer=fn;}observe(){}};
 const scenes=[0,1].map((_,i)=>{
  const recipe=new Element(),canvas=new Element(),fallback=new Element();recipe.hidden=i!==0;recipe.dataset.recipeCategory='creative-interactive';
  const ctx={draws:0,fillRect(){this.draws++;},beginPath(){},moveTo(){},lineTo(){},stroke(){}};
  canvas.getContext=()=>noCanvas?null:ctx;canvas.hidden=true;canvas.getBoundingClientRect=()=>({left:0,top:0,width:640,height:360});
  const choices=[0,1,2,3].map(n=>{const b=new Element();b.dataset.choiceLabel='候选'+n;b.dataset.choiceKind=n===3?'escape':'action';b.setAttribute('aria-pressed','false');b.click=()=>{choices.forEach(x=>x.setAttribute('aria-pressed',String(x===b)));root.fire('click',{target:{closest:()=>b}});};return b;});
  const machine=new Element();recipe.nodes={'.pixel-scene':canvas,'.pixel-fallback':fallback,'.choice-machine':machine};recipe.lists={'[data-choice]':choices};return {recipe,canvas,ctx,fallback,choices,machine};
 });
 root.lists['.recipe']=scenes.map(s=>s.recipe);doc.nodes={'.recipe-section':root,'#pixel-pause':pause};pause.hidden=true;
 api.mount(doc,win);
 const frame=t=>{const queued=[...frames.values()];frames.clear();queued.forEach(fn=>fn(t));};
 const visibility=(scene,value)=>observer([{target:scene.canvas,isIntersecting:value}]);
 return {root,pause,doc,win,motion,frames,scenes,frame,visibility};
}
const h=setup();const a=h.scenes[0],b=h.scenes[1];
assert.equal(a.canvas.hidden,false);assert.equal(a.fallback.getAttribute('hidden'),'');assert.equal(h.frames.size,0,'offscreen renderer starts no RAF');
h.visibility(a,true);assert.equal(h.frames.size,1);h.frame(0);h.frame(40);assert.equal(h.frames.size,1,'one frame owner');
a.choices[2].click();assert.match(a.canvas.getAttribute('aria-label'),/候选2.*路线 3/);assert.equal(h.frames.size,1,'repeated input does not duplicate loops');
h.pause.fire('click');assert.equal(h.frames.size,0);const frozen=a.ctx.draws;
a.canvas.fire('pointermove',{clientX:120,clientY:120});assert.equal(a.ctx.draws,frozen,'paused hover stays still');
a.choices[1].click();assert.match(a.canvas.getAttribute('aria-label'),/候选1.*路线 2/);assert.ok(a.ctx.draws>frozen,'paused choice updates the static result');assert.equal(h.frames.size,0);
h.pause.fire('click');assert.equal(h.frames.size,1);
h.doc.hidden=true;h.doc.fire('visibilitychange');assert.equal(h.frames.size,0);
h.doc.hidden=false;h.doc.fire('visibilitychange');assert.equal(h.frames.size,1);
h.visibility(a,false);assert.equal(h.frames.size,0);
h.visibility(a,true);h.motion.matches=true;h.motion.fire('change');assert.equal(h.frames.size,0);assert.equal(h.pause.disabled,true);
h.motion.matches=false;h.motion.fire('change');assert.equal(h.frames.size,0,'reduced motion does not auto-resume');h.pause.fire('click');
a.recipe.hidden=true;b.recipe.hidden=false;h.root.fire('input');assert.equal(h.frames.size,0,'switching to offscreen scene releases old loop');h.visibility(b,true);assert.equal(h.frames.size,1);
h.visibility(b,false);h.visibility(b,true);assert.equal(h.frames.size,1);
// Real pointer cancellation/drag/secondary pointers cannot choose a route.
const end=api.route(0,4).at(-1),down={pointerId:4,isPrimary:true,button:0,clientX:610,clientY:end[1]*2};
b.canvas.fire('pointerdown',down);b.canvas.fire('pointercancel');b.canvas.fire('pointerup',down);assert.equal(b.choices[0].getAttribute('aria-pressed'),'false');
b.canvas.fire('pointerdown',down);b.canvas.fire('pointerup',{...down,clientY:down.clientY+50});assert.equal(b.choices[0].getAttribute('aria-pressed'),'false');
b.canvas.fire('pointerdown',down);b.canvas.fire('pointerup',{...down,pointerId:9,isPrimary:false});b.canvas.fire('pointerup',down);assert.equal(b.choices[0].getAttribute('aria-pressed'),'true');
const reduced=setup({reduced:true});reduced.visibility(reduced.scenes[0],true);assert.equal(reduced.frames.size,0);assert.equal(reduced.pause.disabled,true);
const fallback=setup({noCanvas:true});assert.equal(fallback.pause.hidden,false,'shared ambient pause remains available without Canvas 2D');assert.equal(fallback.scenes[0].canvas.hidden,true);assert.equal(fallback.scenes[0].fallback.getAttribute('hidden'),null);
// Synthetic terminal outcomes flow from the same machine state and never light an action.
b.choices.forEach(x=>x.setAttribute('aria-pressed','false'));
for(const outcome of ['refusal','error']){
 b.machine.dataset.outcome=outcome;h.root.fire('click',{target:{closest:()=>null}});
 assert.match(b.canvas.getAttribute('aria-label'),new RegExp(`离线示例.*outcome=${outcome}.*没有选中任何选项.*未发送请求`));
 assert.equal(b.canvas.dataset.outcome,outcome);
}
b.machine.dataset.outcome='unknown';b.choices[3].click();assert.match(b.canvas.getAttribute('aria-label'),/保留判断.*outcome=unknown/);
assert.equal(api.outcomeOf(['action','context','escape'],-1),null,'idle is not a successful result');
// Every node must be reachable through its whole drawn square, without another
// route stealing an edge click (especially unknown and the bottom action).
for(const kinds of [['action','action','context','escape'],['action','action','action','action','context','escape']]){
 for(let i=0;i<kinds.length;i++){
  const [x,y]=api.endpoint(kinds,i,kinds.length);
  for(const dx of [7,12,17])for(const dy of [-5,0,5])assert.equal(api.hitRoute(x+dx,y+dy,kinds.length,kinds),i);
 }
}
console.log('Pixel routes, manual selection, pause/reduced motion, visibility, cancellation and fallback checks passed.');
