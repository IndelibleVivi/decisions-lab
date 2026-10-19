'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
 constructor(text=''){
  this.textContent=text;this.hidden=true;this.value='';this.dataset={};this.events={};this.attrs={};this.nodes={};this.lists={};
  const classes=new Set();this.classList={add:k=>classes.add(k),contains:k=>classes.has(k),toggle:(k,on)=>on?classes.add(k):classes.delete(k)};
 }
 addEventListener(type,fn){this.events[type]=fn;}setAttribute(k,v){this.attrs[k]=v;}removeAttribute(k){delete this.attrs[k];}
 querySelector(k){return this.nodes[k]??=new Element();}querySelectorAll(k){return this.lists[k]||[];}
 fire(type){return this.events[type]?.();}
}
function setup(clipboard,hash=''){
 const root=new Element(),groups=['all','creative-interactive','reading-research'].map(id=>{const e=new Element();e.dataset.recipeGroup=id;return e;});
 const recipes=['NPC 剧情 choice','阅读证据 source','中文 NPC 互动'].map((text,i)=>{
  const e=new Element(text);e.id=`recipe-${i}`;e.dataset.recipeCategory=i===1?'reading-research':'creative-interactive';
  e.querySelector('.recipe-payload').textContent=JSON.stringify({question:text});
  e.lists['[data-choice]']=['友好配合','unknown','需要更多设定','直接拒绝','都不适用'].map((text,j)=>{const b=new Element(text);b.dataset={choice:String(j),choiceLabel:text,choiceKind:j===1?'escape':j===2?'context':'action'};return b;});
  e.lists['[data-choice-wire]']=[0,1,2,3,4].map(j=>{const w=new Element();w.dataset.choiceWire=String(j);return w;});
  e.lists['[data-outcome-example]']=['refusal','error'].map(key=>{const b=new Element();b.dataset.outcomeExample=key;return b;});
  e.lists['[data-outcome-state]']=['ok','unknown','refusal','error'].map(key=>{const b=new Element();b.dataset.outcomeState=key;return b;});
  e.lists['.choice-static']=[new Element(),new Element()];return e;
 });
 const selectors=recipes.map(r=>{const b=new Element();b.dataset.recipeSelect=r.id;return b;});
 root.lists={'.recipe':recipes,'[data-recipe-select]':selectors,'[data-recipe-group]':groups};
 const window=new Element();window.location={hash};window.history={replaceState(_,__,next){window.location.hash=next;}};
 vm.runInNewContext(fs.readFileSync('site/recipes.js','utf8'),{document:{querySelector:()=>root},navigator:clipboard?{clipboard}:{},window});
 return {root,groups,recipes,selectors,window,search:root.querySelector('#recipe-search')};
}
async function main(){
 let copied='',fail=false;
 const {root,groups,recipes,selectors,window,search}=setup({async writeText(text){if(fail)throw Error('blocked');copied=text;}});
 assert.equal(root.querySelector('.recipe-tools').hidden,false);
 assert.equal(root.querySelector('.recipe-selectors').hidden,false);
 assert.equal(root.classList.contains('is-enhanced'),true);
 assert.deepEqual(recipes.map(r=>r.hidden),[false,true,true],'one recipe is visible on entry');
 assert.deepEqual(selectors.map(r=>r.hidden),[false,true,false],'creative recipes are the default index');
 assert.equal(groups[1].attrs['aria-pressed'],'true');
 selectors[2].fire('click');assert.deepEqual(recipes.map(r=>r.hidden),[true,true,false]);assert.equal(selectors[2].attrs['aria-current'],'true');assert.equal(window.location.hash,'#recipe-2','explicit recipe selection produces a shareable fragment');
 assert.equal(recipes[2].open,true,'the visible details element must be open');
 search.value='nPc';search.fire('input');assert.equal(root.querySelector('#recipe-count').textContent,'2 / 3 个玩法');
 assert.equal(recipes[2].hidden,false,'a still-matching selection is preserved');
 search.value='not-found';search.fire('input');assert.equal(root.querySelector('#recipe-empty').hidden,false);assert.ok(recipes.every(r=>r.hidden));
 search.value='';search.fire('input');groups[0].fire('click');assert.ok(selectors.every(r=>!r.hidden));assert.equal(root.querySelector('#recipe-empty').hidden,true);
 groups[2].fire('click');assert.deepEqual(recipes.map(r=>r.hidden),[true,false,true],'changing category picks a matching recipe');
 // Visual routes and the human-readable preview agree without changing the task contract.
 const choice=recipes[1].lists['[data-choice]'],wires=recipes[1].lists['[data-choice-wire]'];
 const payload=recipes[1].querySelector('.recipe-payload').textContent;
 const machine=recipes[1].querySelector('.choice-machine'),outcome=recipes[1].querySelector('[data-result-outcome]'),resultChoice=recipes[1].querySelector('[data-result-choice]');
 assert.equal(machine.dataset.previewMode,'idle');assert.equal(outcome.textContent,'—','entry must not invent an answer');
 choice[1].fire('click');assert.equal(choice[1].attrs['aria-pressed'],'true');assert.equal(choice[0].attrs['aria-pressed'],'false');
 assert.equal(wires[1].classList.contains('is-selected'),true);assert.equal(wires[0].classList.contains('is-selected'),false);
 assert.match(recipes[1].querySelector('.choice-readout').textContent,/unknown.*非模型回答/);
 assert.equal(outcome.textContent,'unknown');assert.equal(resultChoice.textContent,'unknown');
 assert.equal(recipes[1].lists['[data-outcome-state]'][1].attrs['aria-current'],'true');
 assert.doesNotMatch(recipes[1].querySelector('.choice-readout').textContent,/第.*动作|都不适用/,'unknown cannot be explained as an ordinary action or an interchangeable domain answer');
 choice[0].fire('click');assert.equal(wires[1].classList.contains('is-selected'),false);assert.equal(wires[0].classList.contains('is-selected'),true);
 assert.equal(outcome.textContent,'ok');assert.equal(recipes[1].lists['[data-outcome-state]'][1].attrs['aria-current'],undefined);
 choice[2].fire('click');assert.equal(outcome.textContent,'ok');assert.match(recipes[1].querySelector('.choice-readout').textContent,/补材料或交人工/);
 for(const index of [3,4]){choice[index].fire('click');assert.equal(outcome.textContent,'ok','domain refusal and none-applicable are ordinary offered choices');}
 for(const example of recipes[1].lists['[data-outcome-example]']){
  example.fire('click');assert.equal(outcome.textContent,example.dataset.outcomeExample);
  assert.ok(choice.every(b=>b.attrs['aria-pressed']==='false'),'refusal/error examples cannot select any option, including unknown');
  assert.ok(wires.every(w=>!w.classList.contains('is-selected')));
  assert.match(resultChoice.textContent,/null/);assert.equal(machine.dataset.previewMode,'example');
  assert.match(recipes[1].querySelector('.choice-readout').textContent,/离线示例.*未发送请求/);
 }
 choice[1].fire('click');assert.equal(machine.dataset.previewMode,'manual');assert.equal(outcome.textContent,'unknown');
 assert.ok(recipes[1].lists['[data-outcome-example]'].every(b=>b.attrs['aria-pressed']==='false'),'manual choice leaves the synthetic error state');
 recipes[1].querySelector('.preview-reset').fire('click');assert.equal(outcome.textContent,'—');assert.equal(machine.dataset.outcome,'');assert.equal(machine.dataset.previewMode,'idle');assert.ok(choice.every(b=>b.attrs['aria-pressed']==='false'));
 assert.equal(recipes[1].querySelector('.recipe-payload').textContent,payload,'preview cannot modify the copied contract');
 await recipes[0].querySelector('.recipe-copy').fire('click');assert.deepEqual(JSON.parse(copied),{question:'NPC 剧情 choice'});
 fail=true;await recipes[1].querySelector('.recipe-copy').fire('click');assert.equal(recipes[1].querySelector('.recipe-payload').hidden,false);assert.match(recipes[1].querySelector('.recipe-copy-status').textContent,/不可用/);
 const fallback=setup();assert.ok(fallback.recipes.every(r=>!r.querySelector('.recipe-payload').hidden),'absent Clipboard API offers manual copy');
 // Recipe fragments work on entry and later navigation, including after a zero-result filter.
 const deep=setup(null,'#recipe-1');assert.equal(deep.recipes[1].hidden,false);assert.equal(deep.groups[0].attrs['aria-pressed'],'true');
 search.value='not-found';search.fire('input');window.location.hash='#recipe-2';window.fire('hashchange');
 assert.equal(recipes[2].hidden,false);assert.equal(search.value,'');assert.equal(groups[0].attrs['aria-pressed'],'true');
 window.location.hash='#%bad';assert.doesNotThrow(()=>window.fire('hashchange'));
 window.location.hash='#experiments';window.fire('hashchange');assert.equal(recipes[2].hidden,false,'unrelated fragments do not reset the workbench');
 console.log('Recipe selection/filter/route-preview/fragment/copy/fallback checks passed.');
}
main().catch(err=>{console.error(err);process.exitCode=1;});
