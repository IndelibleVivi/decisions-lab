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
  removeAttribute(key){delete this.attributes[key];}
  setPointerCapture(id){this.captured=id;}
  releasePointerCapture(id){if(this.captured===id)this.captured=null;}
  getBoundingClientRect(){return {width:1000,height:600,left:0,top:0};}
  querySelector(){return this.child??=new Node();}
}
function motionTest(file,prefix) {
  function setup(reduce) {
    const nodes=new Map();const get=selector=>{if(!nodes.has(selector))nodes.set(selector,new Node());return nodes.get(selector);};
    const doc=new Node();doc.hidden=false;doc.documentElement={dataset:{theme:'light'}};
    doc.querySelector=get;doc.querySelectorAll=selector=>[0,1,2].map(i=>get(selector+i));
    let draws=0;const uniforms={};
    const context=new Proxy({}, {get:(_,key)=>{
      if(key==='clearRect'||key==='clear')return ()=>draws++;
      if(key==='getShaderParameter'||key==='getProgramParameter')return ()=>true;
      if(key==='getUniformLocation')return (_,name)=>name;
      if(['uniform3fv','uniform2fv','uniform1fv'].includes(key))return (name,value)=>{assert.ok([...value].every(Number.isFinite),'finite GPU uniforms');uniforms[name]=[...value];};
      if(key==='uniform1f')return (name,value)=>{assert.ok(Number.isFinite(value),'finite GPU scalar');uniforms[name]=value;};
      if(key==='bufferData')return (_,value)=>assert.ok([...value].every(Number.isFinite),'finite point geometry');
      return ()=>{};
    },set:()=>true});
    const canvas=get(prefix==='sculpture'?'#sculpture-canvas':'#probability-field');canvas.getContext=()=>context;
    const media=new Node();media.matches=reduce;
    let intersect;let id=0;const pending=new Map();
    const win=new Node();
    const env={document:doc,window:win,matchMedia:()=>media,devicePixelRatio:1,console,
      requestAnimationFrame:fn=>{pending.set(++id,fn);return id;},cancelAnimationFrame:id=>pending.delete(id),
      ResizeObserver:class {observe(){}},IntersectionObserver:class{constructor(fn){intersect=fn;}observe(){}}};
    vm.runInNewContext(fs.readFileSync(`site/${file}`,'utf8'),env);
    return {get,doc,win,media,pending,uniforms,draws:()=>draws,intersect:value=>intersect([{isIntersecting:value}]),intersectBatch:values=>intersect(values.map(isIntersecting=>({isIntersecting}))),
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
  if(prefix==='sculpture') {
    runtime.get('[data-sculpture-mode]1').fire('click');
    check(JSON.stringify(runtime.uniforms.uMorph)==='[0,1,0]','paused mode selection produces requested geometry immediately');
    check(runtime.pending.size===0,'mode selection respects pause');
    runtime.get('#sculpture-burst').fire('click');
    check(runtime.uniforms.uBurst===1.5&&runtime.pending.size===0,'paused burst is one static state');
    runtime.get('#sculpture-burst').fire('click');
    check(runtime.uniforms.uBurst===0,'paused burst toggles back to assembled form');
    runtime.get('#sculpture-canvas').dispatchEvent({type:'webglcontextlost',preventDefault(){}});
    check(runtime.pending.size===0&&runtime.get('#sculpture-canvas').hidden,'context loss stops loop and hides canvas');
    check(!('hidden' in runtime.get('.sculpture-fallback').attributes),'context loss restores static fallback');
    runtime.get('#sculpture-canvas').fire('webglcontextrestored');
    check(!runtime.get('#sculpture-canvas').hidden&&runtime.pending.size===0,'context restore respects paused state');
    check(runtime.get('#sculpture-status').textContent==='粒子作品已恢复；当前已暂停。','context restore replaces stale failure announcement');
  }
  const before=runtime.draws();runtime.doc.documentElement.dataset.theme='dark';runtime.doc.fire('themechange');
  check(runtime.draws()>before&&runtime.pending.size===0,`${file}: theme repaints paused artwork without restarting`);
  if(prefix==='sculpture') {
    const pevent=(type,extra={})=>{const e=Object.assign({type,defaultPrevented:false,target:{closest:()=>null},preventDefault(){e.defaultPrevented=true;}},extra);return e;};
    const nested={closest:selector=>selector.indexOf('button')>=0?{}:null};
    // Hover eases whole-object yaw and pitch while playing.
    const hov=setup(false);hov.intersect(true);hov.frame(100);hov.frame(150);
    const hst=hov.get('.cover-stage'),hy0=hov.uniforms.uYaw,hp0=hov.uniforms.uPitch;
    const ctrl=setup(false);ctrl.intersect(true);ctrl.frame(100);ctrl.frame(150);const ctrlYaw0=ctrl.uniforms.uYaw;
    hst.dispatchEvent(pevent('pointermove',{clientX:980,clientY:40}));
    for(let i=0;i<10;i++){hov.frame(200+i*50);ctrl.frame(200+i*50);}
    const idleDrift=ctrl.uniforms.uYaw-ctrlYaw0;
    check(hov.uniforms.uPitch-hp0>0.05,`${file}: hover tilts whole-object pitch`);
    check(hov.uniforms.uYaw-hy0<idleDrift-0.05,`${file}: hover yaws whole object beyond idle spin`);
    // Hover alone must not animate a paused or reduced-motion scene.
    const ph=setup(true);ph.intersect(true);
    const phPitch=ph.uniforms.uPitch,phYaw=ph.uniforms.uYaw;
    ph.get('.cover-stage').dispatchEvent(pevent('pointermove',{clientX:980,clientY:40}));
    check(ph.pending.size===0&&ph.uniforms.uPitch===phPitch&&ph.uniforms.uYaw===phYaw,`${file}: paused hover stays static`);
    // Deliberate drag rotates the object and never bursts.
    const dr=setup(false);dr.intersect(true);dr.frame(100);dr.frame(150);
    const dst=dr.get('.cover-stage'),dragYaw0=dr.uniforms.uYaw;
    dst.dispatchEvent(pevent('pointerdown',{button:0,pointerId:7,clientX:500,clientY:300,timeStamp:1000}));
    dst.dispatchEvent(pevent('pointermove',{button:0,pointerId:7,clientX:700,clientY:300,timeStamp:1016}));
    dst.dispatchEvent(pevent('pointermove',{button:0,pointerId:7,clientX:900,clientY:300,timeStamp:1032}));
    dr.frame(200);
    check(dr.uniforms.uYaw-dragYaw0>0.5,`${file}: drag rotates whole object`);
    dst.dispatchEvent(pevent('pointerup',{button:0,pointerId:7,clientX:900,clientY:300,timeStamp:1100}));
    dr.frame(250);
    check(dr.uniforms.uBurst===0,`${file}: drag release does not burst`);
    let inertia=dr.uniforms.uYaw,inertiaPeak=0,inertiaStep=0;
    for(let i=1;i<=30;i++){dr.frame(250+i*50);inertiaStep=Math.abs(dr.uniforms.uYaw-inertia);inertia=dr.uniforms.uYaw;if(i<=8)inertiaPeak=Math.max(inertiaPeak,inertiaStep);}
    check(inertiaPeak<=0.22,`${file}: inertial release stays bounded`);
    check(inertiaStep<0.03,`${file}: inertial release settles to idle spin`);
    // A short clean tap may burst; a drag and control clicks must not.
    const tap=setup(false);tap.intersect(true);tap.frame(100);
    const tst=tap.get('.cover-stage');
    tst.dispatchEvent(pevent('pointerdown',{button:0,pointerId:3,clientX:500,clientY:300,timeStamp:2000}));
    tst.dispatchEvent(pevent('pointerup',{button:0,pointerId:3,clientX:501,clientY:300,timeStamp:2100}));
    tap.frame(150);
    check(tap.uniforms.uBurst>1,`${file}: clean tap bursts`);
    const guarded=setup(false);guarded.intersect(true);guarded.frame(100);
    const gst=guarded.get('.cover-stage');
    gst.dispatchEvent(pevent('pointerdown',{button:0,pointerId:4,clientX:500,clientY:300,timeStamp:2200,target:nested}));
    gst.dispatchEvent(pevent('pointerup',{button:0,pointerId:4,clientX:500,clientY:300,timeStamp:2210,target:nested}));
    guarded.frame(150);
    check(guarded.uniforms.uBurst===0,`${file}: nested controls keep their own clicks`);
    // pointercancel ends a drag so later movement is only hover.
    const ca=setup(false);ca.intersect(true);ca.frame(100);ca.frame(150);
    const cst=ca.get('.cover-stage');
    cst.dispatchEvent(pevent('pointerdown',{button:0,pointerId:9,clientX:200,clientY:300,timeStamp:3000}));
    cst.dispatchEvent(pevent('pointermove',{button:0,pointerId:9,clientX:400,clientY:300,timeStamp:3016}));
    ca.frame(200);
    const cancelYaw=ca.uniforms.uYaw;
    cst.dispatchEvent(pevent('pointercancel',{pointerId:9}));
    cst.dispatchEvent(pevent('pointermove',{button:0,pointerId:9,clientX:900,clientY:300,timeStamp:3032}));
    for(let i=0;i<10;i++)ca.frame(250+i*50);
    check(ca.uniforms.uYaw-cancelYaw<0.6,`${file}: pointercancel ends the drag`);
    // Hiding the tab ends a drag safely; returning resumes exactly one loop.
    const hid=setup(false);hid.intersect(true);hid.frame(100);hid.frame(150);
    const hidst=hid.get('.cover-stage');
    hidst.dispatchEvent(pevent('pointerdown',{button:0,pointerId:21,clientX:300,clientY:300,timeStamp:500}));
    hidst.dispatchEvent(pevent('pointermove',{button:0,pointerId:21,clientX:500,clientY:300,timeStamp:516}));
    hid.doc.hidden=true;hid.doc.fire('visibilitychange');
    check(hid.pending.size===0,`${file}: hidden tab stops a drag loop`);
    hid.doc.hidden=false;hid.doc.fire('visibilitychange');
    check(hid.pending.size===1,`${file}: visible tab resumes once after a drag`);
    hid.frame(600);
    const hiddenYaw=hid.uniforms.uYaw;
    hidst.dispatchEvent(pevent('pointermove',{button:0,pointerId:21,clientX:900,clientY:300,timeStamp:616}));
    for(let i=0;i<8;i++)hid.frame(700+i*50);
    check(hid.uniforms.uYaw-hiddenYaw<0.5,`${file}: visibility change ended the drag`);
    // Keyboard rotates and resets; it must never steal keys from nested controls.
    const kb=setup(false);kb.intersect(true);kb.frame(100);kb.frame(150);
    const kbst=kb.get('.cover-stage'),keyYaw0=kb.uniforms.uYaw,keyPitch0=kb.uniforms.uPitch;
    const right=pevent('keydown',{key:'ArrowRight'});
    kbst.dispatchEvent(right);kb.frame(200);
    check(kb.uniforms.uYaw-keyYaw0>0.25&&right.defaultPrevented,`${file}: arrow keys rotate and prevent scroll`);
    kbst.dispatchEvent(pevent('keydown',{key:'ArrowUp'}));kb.frame(250);
    check(kb.uniforms.uPitch<keyPitch0-0.2,`${file}: arrow keys tilt pitch`);
    kbst.dispatchEvent(pevent('keydown',{key:'Home'}));kb.frame(300);
    check(Math.abs(kb.uniforms.uPitch-keyPitch0)<1e-9&&Math.abs(kb.uniforms.uYaw-keyYaw0)<0.05,`${file}: Home resets the pose`);
    const guardedKey=pevent('keydown',{key:'ArrowUp',target:nested});
    const keyPitchBefore=kb.uniforms.uPitch;
    kbst.dispatchEvent(guardedKey);kb.frame(350);
    check(kb.uniforms.uPitch===keyPitchBefore&&!guardedKey.defaultPrevented,`${file}: nested controls keep arrow keys`);
    // Paused or reduced motion keeps direct input static, with no inertia loop.
    const still=setup(true);still.intersect(true);
    const stillst=still.get('.cover-stage'),stillPitch=still.uniforms.uPitch,stillYaw=still.uniforms.uYaw;
    stillst.dispatchEvent(pevent('keydown',{key:'ArrowUp'}));
    check(still.pending.size===0&&still.uniforms.uPitch<stillPitch-0.2,`${file}: paused arrows rotate a static frame`);
    stillst.dispatchEvent(pevent('pointerdown',{button:0,pointerId:11,clientX:500,clientY:300,timeStamp:100}));
    stillst.dispatchEvent(pevent('pointermove',{button:0,pointerId:11,clientX:700,clientY:300,timeStamp:116}));
    check(still.pending.size===0&&still.uniforms.uYaw>stillYaw+0.5,`${file}: paused drag rotates without animating`);
    stillst.dispatchEvent(pevent('pointerup',{button:0,pointerId:11,clientX:700,clientY:300,timeStamp:200}));
    check(still.uniforms.uBurst===0,`${file}: paused drag does not burst`);
    stillst.dispatchEvent(pevent('keydown',{key:'Home'}));
    check(still.uniforms.uPitch===stillPitch&&still.uniforms.uYaw===stillYaw&&still.pending.size===0,`${file}: paused Home restores the static pose`);
    // Context loss during a drag stops the loop instead of leaving it half-active.
    const cl=setup(false);cl.intersect(true);cl.frame(100);cl.frame(150);
    const clst=cl.get('.cover-stage');
    clst.dispatchEvent(pevent('pointerdown',{button:0,pointerId:31,clientX:300,clientY:300,timeStamp:400}));
    clst.dispatchEvent(pevent('pointermove',{button:0,pointerId:31,clientX:500,clientY:300,timeStamp:416}));
    cl.get('#sculpture-canvas').dispatchEvent({type:'webglcontextlost',preventDefault(){}});
    clst.dispatchEvent(pevent('pointermove',{button:0,pointerId:31,clientX:900,clientY:300,timeStamp:432}));
    check(cl.pending.size===0&&cl.get('#sculpture-canvas').hidden,`${file}: context loss during a drag stops safely`);
    check(clst.captured===null,`${file}: context loss releases pointer capture`);
    const guard=setup(true),stage=guard.get('.cover-stage');
    const point=(type,id,x=500)=>pevent(type,{pointerId:id,button:0,clientX:x,clientY:300,timeStamp:100});
    stage.dispatchEvent(point('pointerdown',1));
    const initialYaw=guard.uniforms.uYaw;
    stage.dispatchEvent(point('pointermove',2,800));stage.dispatchEvent(point('pointerup',2));
    check(guard.uniforms.uYaw===initialYaw&&stage.captured===1,`${file}: another pointer cannot move or release the active drag`);
    stage.dispatchEvent(point('pointercancel',1));stage.dispatchEvent(point('pointerup',1));
    check(guard.uniforms.uBurst===0&&stage.captured===null,`${file}: cancelled press cannot burst on a late release`);
    stage.dispatchEvent(point('pointerdown',1));guard.win.fire('blur');stage.dispatchEvent(point('pointerup',1));
    check(guard.uniforms.uBurst===0&&stage.captured===null,`${file}: blur releases capture and invalidates the press`);
    guard.get('[data-sculpture-mode]2').fire('click');guard.get('#sculpture-burst').fire('click');
    stage.dispatchEvent(pevent('keydown',{key:'ArrowRight'}));guard.get('#sculpture-reset').fire('click');
    check(guard.uniforms.uBurst===0&&guard.uniforms.uYaw===-.30&&guard.uniforms.uPitch===-.38,`${file}: reset clears scatter and restores initial viewpoint`);
    check(JSON.stringify(guard.uniforms.uMorph)==='[0,0,1]'&&guard.pending.size===0,`${file}: reset keeps selected shape and pause`);
    check(guard.uniforms.uTrailW.every(x=>x===0)&&guard.uniforms.uActive===0,`${file}: reset clears pointer deformation`);
    const latest=setup(false);latest.intersectBatch([false,true]);
    check(latest.pending.size===1,`${file}: newest observer entry controls visibility`);
  }
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
