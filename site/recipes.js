// Catalog → selector → one inspectable recipe. Preview choices never call a model.
(function () {
  'use strict';
  const root=document.querySelector('.recipe-section');if(!root)return;
  const recipes=[...root.querySelectorAll('.recipe')];
  const selectors=[...root.querySelectorAll('[data-recipe-select]')];
  const search=root.querySelector('#recipe-search');
  const buttons=[...root.querySelectorAll('[data-recipe-group]')];
  const count=root.querySelector('#recipe-count'),empty=root.querySelector('#recipe-empty');
  const searchable=new Map(recipes.map(recipe=>[recipe,recipe.textContent.toLocaleLowerCase()]));
  let group='creative-interactive',selected=null,matching=[];
  function select(recipe){
    selected=recipe;
    for(const item of recipes){item.hidden=item!==recipe;item.open=item===recipe;}
    for(const button of selectors)button.setAttribute('aria-current',String(button.dataset.recipeSelect===recipe?.id));
  }
  function filter(){
    const query=search.value.trim().toLocaleLowerCase();
    matching=recipes.filter(recipe=>(group==='all'||recipe.dataset.recipeCategory===group)&&searchable.get(recipe).includes(query));
    const ids=new Set(matching.map(recipe=>recipe.id));
    for(const button of selectors)button.hidden=!ids.has(button.dataset.recipeSelect);
    for(const button of buttons)button.setAttribute('aria-pressed',String(button.dataset.recipeGroup===group));
    select(matching.includes(selected)?selected:matching[0]||null);
    count.textContent=`${matching.length} / ${recipes.length} 个玩法`;empty.hidden=matching.length!==0;
  }
  for(const button of buttons)button.addEventListener('click',()=>{
    group=button.dataset.recipeGroup;filter();
  });
  for(const button of selectors)button.addEventListener('click',()=>select(recipes.find(recipe=>recipe.id===button.dataset.recipeSelect)));
  search.addEventListener('input',filter);
  for(const recipe of recipes){
    const choices=[...recipe.querySelectorAll('[data-choice]')];
    const wires=[...recipe.querySelectorAll('[data-choice-wire]')];
    const machine=recipe.querySelector('.choice-machine');
    for(const label of recipe.querySelectorAll('.choice-static'))label.hidden=true;
    recipe.querySelector('.choice-readout').textContent='点选候选，预览一条分支 · 不调用模型';
    for(const choice of choices){
      choice.hidden=false;
      choice.addEventListener('click',()=>{
        for(const button of choices)button.setAttribute('aria-pressed',String(button===choice));
        for(const wire of wires)wire.classList.toggle('is-selected',wire.dataset.choiceWire===choice.dataset.choice);
        machine.classList.add('is-picked');
        recipe.querySelector('.choice-readout').textContent=`手动试选：${choice.dataset.choiceLabel} · 非模型回答`;
      });
    }
    const copy=recipe.querySelector('.recipe-copy');
    const status=recipe.querySelector('.recipe-copy-status'),payload=recipe.querySelector('.recipe-payload');
    if(!navigator.clipboard?.writeText){payload.hidden=false;status.textContent='可从下方选择复制任务 JSON。';continue;}
    copy.hidden=false;copy.addEventListener('click',async()=>{
      try{await navigator.clipboard.writeText(payload.textContent);status.textContent='已复制任务 JSON。';}
      catch(_){payload.hidden=false;status.textContent='剪贴板不可用，请从下方选择复制。';}
    });
  }
  function followFragment(){
    let id;try{id=decodeURIComponent(window.location.hash.slice(1));}catch(_){return;}
    const recipe=recipes.find(item=>item.id===id);if(!recipe)return;
    group='all';search.value='';selected=recipe;filter();
  }
  root.classList.add('is-enhanced');
  root.querySelector('.recipe-tools').hidden=false;
  root.querySelector('.recipe-selectors').hidden=false;
  filter();followFragment();
  window.addEventListener('hashchange',followFragment);
})();
