// Progressive enhancement for the canonical recipe catalog. No network or storage.
(function () {
  'use strict';
  const root=document.querySelector('.recipe-section');if(!root)return;
  const recipes=[...root.querySelectorAll('.recipe')];
  const search=root.querySelector('#recipe-search');
  const buttons=[...root.querySelectorAll('[data-recipe-group]')];
  const count=root.querySelector('#recipe-count'),empty=root.querySelector('#recipe-empty');
  let group='all';
  function filter(){
    const query=search.value.trim().toLocaleLowerCase();let found=0;
    for(const recipe of recipes){
      const match=(group==='all'||recipe.dataset.recipeCategory===group)&&recipe.textContent.toLocaleLowerCase().includes(query);
      recipe.hidden=!match;if(match)found++;
    }
    count.textContent=`${found} / ${recipes.length} 个玩法`;empty.hidden=found!==0;
  }
  for(const button of buttons)button.addEventListener('click',()=>{
    group=button.dataset.recipeGroup;for(const b of buttons)b.setAttribute('aria-pressed',String(b===button));filter();
  });
  search.addEventListener('input',filter);
  for(const recipe of recipes){
    const copy=recipe.querySelector('.recipe-copy');
    const status=recipe.querySelector('.recipe-copy-status'),payload=recipe.querySelector('.recipe-payload');
    if(!navigator.clipboard?.writeText){payload.hidden=false;status.textContent='可从下方选择复制任务 JSON。';continue;}
    copy.hidden=false;copy.addEventListener('click',async()=>{
      try{await navigator.clipboard.writeText(payload.textContent);status.textContent='已复制任务 JSON。';}
      catch(_){payload.hidden=false;status.textContent='剪贴板不可用，请从下方选择复制。';}
    });
  }
  root.querySelector('.recipe-tools').hidden=false;filter();
})();
