// Deterministic runtime checks for motion lifecycle, distributions and theme.
// Canvas drawing is stubbed here; real composition is checked in a browser.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {entropy,withFirst,presets} = require('../site/field.js');
let checks=0;
function check(condition,message) { assert.ok(condition,message);checks++; }
check(Math.abs(entropy([1/3,1/3,1/3])-Math.log2(3))<1e-12,'uniform entropy');
check(entropy([1,0,0])===0,'one-hot entropy');
for(const p of presets) check(Math.abs(p.reduce((a,b)=>a+b)-1)<1e-12,'preset normalizes');
for(const a of [0,.36,.72,1]) {
  const p=withFirst(a,5/7);
  check(Math.abs(p.reduce((x,y)=>x+y)-1)<1e-12&&p.every(x=>x>=0),'slider keeps simplex');
  if(a<1) check(Math.abs(p[1]/(p[1]+p[2])-5/7)<1e-12,'slider retains B:C ratio');
}
class Node {
  constructor(){this.listeners={};this.attributes={};this.hidden=true;this.textContent='';this.dataset={};}
  addEventListener(name,fn){(this.listeners[name]??=[]).push(fn);}
  dispatchEvent(event){for(const fn of this.listeners[event.type]||[]) fn(event);}
  fire(type){this.dispatchEvent({type});}
  setAttribute(key,value){this.attributes[key]=value;}
  getBoundingClientRect(){return {width:1000,height:600,left:0,top:0};}
  querySelector(){return this.child??=new Node();}
}
function motionTest(file,prefix) {
  function setup(reduce) {
    const nodes=new Map();const get=selector=>{if(!nodes.has(selector))nodes.set(selector,new Node());return nodes.get(selector);};
    const doc=new Node();doc.hidden=false;doc.documentElement={dataset:{theme:'light'}};
    doc.querySelector=get;doc.querySelectorAll=selector=>[0,1,2].map(i=>get(selector+i));
    let draws=0; const context=new Proxy({}, {get:(_,key)=>key==='clearRect'?()=>draws++:()=>{},set:()=>true});
    const canvas=get(prefix==='sculpture'?'#sculpture-canvas':'#probability-field');canvas.getContext=()=>context;
    const media=new Node();media.matches=reduce;
    let intersect;let id=0;const pending=new Map();
    const env={document:doc,matchMedia:()=>media,devicePixelRatio:1,console,
      requestAnimationFrame:fn=>{pending.set(++id,fn);return id;},cancelAnimationFrame:id=>pending.delete(id),
      ResizeObserver:class {observe(){}},IntersectionObserver:class{constructor(fn){intersect=fn;}observe(){}}};
    vm.runInNewContext(fs.readFileSync(`site/${file}`,'utf8'),env);
    return {get,doc,media,pending,draws:()=>draws,intersect:value=>intersect([{isIntersecting:value}]),
      frame:stamp=>{const [id,fn]=pending.entries().next().value;pending.delete(id);fn(stamp);}};
  }
  const reduced=setup(true);
  check(reduced.pending.size===0,`${file}: reduced motion starts still`);
  check(reduced.get(`#${prefix}-pause`).attributes['aria-pressed']==='true',`${file}: reduced motion UI`);
  const runtime=setup(false),button=runtime.get(`#${prefix}-pause`);
  check(runtime.get(`.${prefix}-fallback`).attributes.hidden==='',`${file}: SVG fallback uses actual hidden attribute`);
  check(runtime.pending.size===1,`${file}: one initial frame`);
  runtime.intersect(true);runtime.intersect(true);
  check(runtime.pending.size===1,`${file}: duplicate visibility cannot multiply loops`);
  runtime.frame(100);runtime.frame(150);
  check(runtime.pending.size===1&&runtime.draws()>1,`${file}: frame advances`);
  button.fire('click');check(runtime.pending.size===0,`${file}: pause cancels frame`);
  runtime.intersect(false);button.fire('click');
  check(runtime.pending.size===0,`${file}: resuming while offscreen remains idle`);
  runtime.intersect(true);check(runtime.pending.size===1,`${file}: reentry resumes`);
  runtime.doc.hidden=true;runtime.doc.fire('visibilitychange');check(runtime.pending.size===0,`${file}: hidden tab stops`);
  runtime.doc.hidden=false;runtime.doc.fire('visibilitychange');check(runtime.pending.size===1,`${file}: visible tab resumes once`);
  runtime.media.matches=true;runtime.media.fire('change');
  check(runtime.pending.size===0&&button.attributes['aria-pressed']==='true',`${file}: switching reduced motion stops`);
  const before=runtime.draws();runtime.doc.documentElement.dataset.theme='dark';runtime.doc.fire('themechange');
  check(runtime.draws()>before&&runtime.pending.size===0,`${file}: theme repaints paused artwork without restarting`);
}
motionTest('sculpture.js','sculpture');motionTest('field.js','field');
function themeTest(storageFails=false) {
  const doc=new Node();doc.documentElement={dataset:{}};const nodes=new Map();doc.querySelector=key=>{if(!nodes.has(key))nodes.set(key,new Node());return nodes.get(key);};
  const media=new Node();media.matches=true;const writes=[];
  vm.runInNewContext(fs.readFileSync('site/theme.js','utf8'),{document:doc,matchMedia:()=>media,Event:class{constructor(type){this.type=type;}},localStorage:{getItem(){if(storageFails)throw Error('denied');return 'invalid';},setItem(k,v){if(storageFails)throw Error('denied');writes.push([k,v]);}}});
  check(doc.documentElement.dataset.theme==='dark','theme follows system without valid saved choice');
  doc.fire('DOMContentLoaded');const button=doc.querySelector('#theme-toggle');
  check(button.attributes['aria-label']==='切换到日间模式','theme button names next action');
  media.matches=false;media.fire('change');check(doc.documentElement.dataset.theme==='light','system changes followed before explicit selection');
  button.fire('click');check(doc.documentElement.dataset.theme==='dark','explicit theme works even with blocked storage');
  media.fire('change');check(doc.documentElement.dataset.theme==='dark','explicit choice wins over system');
  if(!storageFails)check(writes.length===1&&writes[0][0]==='decisions-theme'&&writes[0][1]==='dark','only appearance preference stored');
}
themeTest();themeTest(true);
console.log(`${checks} visual runtime checks passed (no browser or provider calls).`);
