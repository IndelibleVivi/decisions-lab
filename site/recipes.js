// Catalog → selector → one inspectable recipe. Preview choices never call a model.
(function () {
  'use strict';
  const root=document.querySelector('.recipe-section');if(!root)return;
  const recipes=[...root.querySelectorAll('.recipe')];
  const selectors=[...root.querySelectorAll('[data-recipe-select]')];
  const shelf=root.querySelector('.recipe-selectors');
  const search=root.querySelector('#recipe-search');
  const buttons=[...root.querySelectorAll('[data-recipe-group]')];
  const count=root.querySelector('#recipe-count'),empty=root.querySelector('#recipe-empty');
  const searchable=new Map(recipes.map(recipe=>[recipe,recipe.textContent.toLocaleLowerCase()]));
  let group='creative-interactive',selected=null,matching=[];
  function select(recipe){
    selected=recipe;
    for(const item of recipes){item.hidden=item!==recipe;item.open=item===recipe;}
    for(const button of selectors)button.setAttribute('aria-current',String(button.dataset.recipeSelect===recipe?.id));
    // Keep the active cartridge in its own scrollable shelf without moving the
    // page away from the working recipe, including on a direct fragment visit.
    const active=selectors.find(button=>button.dataset.recipeSelect===recipe?.id);
    if(active&&(shelf.scrollWidth>shelf.clientWidth||shelf.scrollHeight>shelf.clientHeight)){
      const frame=shelf.getBoundingClientRect(),target=active.getBoundingClientRect();
      shelf.scrollLeft+=target.left<frame.left?target.left-frame.left:target.right>frame.right?target.right-frame.right:0;
      shelf.scrollTop+=target.top<frame.top?target.top-frame.top:target.bottom>frame.bottom?target.bottom-frame.bottom:0;
    }
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
  for(const button of selectors)button.addEventListener('click',()=>{
    const recipe=recipes.find(item=>item.id===button.dataset.recipeSelect);
    select(recipe);
    if(recipe)window.history.replaceState(null,'',`#${recipe.id}`);
  });
  search.addEventListener('input',filter);
  for(const recipe of recipes){
    const choices=[...recipe.querySelectorAll('[data-choice]')];
    const wires=[...recipe.querySelectorAll('[data-choice-wire]')];
    const machine=recipe.querySelector('.choice-machine');
    const examples=[...recipe.querySelectorAll('[data-outcome-example]')];
    const states=[...recipe.querySelectorAll('[data-outcome-state]')];
    const reset=recipe.querySelector('.preview-reset');
    const readout=recipe.querySelector('.choice-readout');
    function preview(choice=null,outcome=null,mode='idle'){
      for(const button of choices)button.setAttribute('aria-pressed',String(button===choice));
      for(const wire of wires)wire.classList.toggle('is-selected',!!choice&&wire.dataset.choiceWire===choice.dataset.choice);
      for(const example of examples)example.setAttribute('aria-pressed',String(mode==='example'&&example.dataset.outcomeExample===outcome));
      for(const state of states){
        const active=state.dataset.outcomeState===outcome;
        state.classList.toggle('is-current',active);
        if(active)state.setAttribute('aria-current','true');else state.removeAttribute('aria-current');
      }
      machine.dataset.outcome=outcome||'';
      machine.dataset.previewMode=mode;
      machine.classList.toggle('is-picked',outcome!==null);
      reset.disabled=outcome===null;
      recipe.querySelector('[data-result-outcome]').textContent=outcome||'—';
      recipe.querySelector('[data-result-choice]').textContent=choice?choice.dataset.choiceLabel:outcome?'null · 未选中任何选项':'—';
      if(!outcome){readout.textContent='尚未试选 · 点文字按钮或图中的方形节点。浏览器不请求模型。';return;}
      if(mode==='example'){
        readout.textContent=outcome==='refusal'
          ?'离线示例：API 拒答（outcome=refusal）。没有选中任何选项；这与角色台词里的「拒绝」不同。未发送请求。'
          :'离线示例：调用失败（outcome=error）。例如网络、HTTP 或响应格式错误；不能当成 unknown。未发送请求。';
        return;
      }
      const explanation=outcome==='unknown'
        ?'显式保留判断（outcome=unknown），没有选中可执行动作'
        :choice.dataset.choiceKind==='context'
          ?'选择补材料或交人工（outcome=ok），这是已有选项中的有效选择'
          :/拒绝|不适用|无适用/.test(choice.dataset.choiceLabel)
            ?'选择已有选项（outcome=ok）；选项文案中的拒绝或不适用，不等于 API 拒答或 unknown'
            :'选择已有选项（outcome=ok），建议不会自动执行';
      readout.textContent=`手动试选：${choice.dataset.choiceLabel} · ${explanation} · 非模型回答`;
    }
    for(const label of recipe.querySelectorAll('.choice-static'))label.hidden=true;
    recipe.querySelector('.response-examples').hidden=false;
    preview();
    for(const choice of choices){
      choice.hidden=false;
      choice.addEventListener('click',()=>{
        preview(choice,choice.dataset.choiceKind==='escape'?'unknown':'ok','manual');
      });
    }
    for(const example of examples)example.addEventListener('click',()=>preview(null,example.dataset.outcomeExample,'example'));
    reset.addEventListener('click',()=>preview());
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
