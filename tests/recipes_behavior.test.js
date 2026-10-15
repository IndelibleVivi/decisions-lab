'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
 constructor(text=''){this.textContent=text;this.hidden=true;this.value='';this.dataset={};this.events={};this.attrs={};this.nodes={};}
 addEventListener(type,fn){this.events[type]=fn;}setAttribute(k,v){this.attrs[k]=v;}
 querySelector(k){return this.nodes[k]??=new Element();}fire(type){return this.events[type]?.();}
}
async function main(){
 const root=new Element(),groups=['all','creative','reading'].map(id=>{const e=new Element();e.dataset.recipeGroup=id;return e;});
 const recipes=['NPC 剧情 choice','阅读证据 source','中文 NPC 互动'].map((text,i)=>{const e=new Element(text);e.dataset.recipeCategory=i===1?'reading':'creative';e.querySelector('.recipe-payload').textContent=JSON.stringify({question:text});return e;});
 root.querySelectorAll=selector=>selector==='.recipe'?recipes:groups;
 let copied='',fail=false;
 vm.runInNewContext(fs.readFileSync('site/recipes.js','utf8'),{document:{querySelector:()=>root},navigator:{clipboard:{async writeText(text){if(fail)throw Error('blocked');copied=text;}}}});
 assert.equal(root.querySelector('.recipe-tools').hidden,false);
 assert.ok(recipes.every(r=>!r.hidden));
 groups[1].fire('click');assert.deepEqual(recipes.map(r=>r.hidden),[false,true,false]);assert.equal(groups[1].attrs['aria-pressed'],'true');
 const search=root.querySelector('#recipe-search');search.value='nPc';search.fire('input');assert.equal(root.querySelector('#recipe-count').textContent,'2 / 3 个玩法');
 search.value='not-found';search.fire('input');assert.equal(root.querySelector('#recipe-empty').hidden,false);assert.ok(recipes.every(r=>r.hidden));
 search.value='';search.fire('input');groups[0].fire('click');assert.ok(recipes.every(r=>!r.hidden));assert.equal(root.querySelector('#recipe-empty').hidden,true);
 await recipes[0].querySelector('.recipe-copy').fire('click');assert.deepEqual(JSON.parse(copied),{question:'NPC 剧情 choice'});
 fail=true;await recipes[1].querySelector('.recipe-copy').fire('click');assert.equal(recipes[1].querySelector('.recipe-payload').hidden,false);assert.match(recipes[1].querySelector('.recipe-copy-status').textContent,/不可用/);
 for(const recipe of recipes)recipe.querySelector('.recipe-payload').hidden=true;
 vm.runInNewContext(fs.readFileSync('site/recipes.js','utf8'),{document:{querySelector:()=>root},navigator:{}});
 assert.ok(recipes.every(r=>!r.querySelector('.recipe-payload').hidden),'absent Clipboard API offers manual copy');
 console.log('Recipe group/search/empty/reset/copy/fallback behavior passed.');
}
main().catch(err=>{console.error(err);process.exitCode=1;});
