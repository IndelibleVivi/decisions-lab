/* Local Studio: native JSON evidence stays on the loopback server. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const sessionToken = document.querySelector('meta[name="studio-token"]')?.content;
  if (!sessionToken || !$('studio-local')) return;
  $('studio-local').hidden=false; $('studio-offline').hidden=true;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const json = value => JSON.stringify(value, null, 2);
  const fmt = value => value == null ? '未知' : typeof value === 'number' ? Number(value.toFixed(6)).toString() : String(value);
  const families = {'api-lab':'E1 / MEASUREMENT', 'active-evidence':'E2 / ACTIVE EVIDENCE', 'typed-dag':'E3 / TYPED DAG'};
  let study = null, draft = null, tab = 'design', analysisId = null, sampleIndex = 0, dirty = false, busy = false;
  let fileConsumer = null, noticeTimer = null;
  function notice(text, error=false) { clearTimeout(noticeTimer); $('status').hidden=false; $('status').textContent=text; $('status').classList.toggle('error',error); if(!error)noticeTimer=setTimeout(()=>$('status').hidden=true,6500); }
  async function api(path, body, raw=false) {
    const response = await fetch(path, body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json','X-Studio-Token':sessionToken}, body:json(body)});
    const text = await response.text();
    if (!response.ok) throw new Error(JSON.parse(text).error || '本地请求失败');
    return raw?text:JSON.parse(text);
  }
  async function perform(fn, message='已保存到本地') {
    if (busy) return;
    busy=true;
    const root=$('studio-local'); root.inert=true; root.setAttribute('aria-busy','true');
    try { await fn(); notice(message); }
    catch(error) { notice(error.message,true); }
    finally { busy=false; root.inert=false; root.removeAttribute('aria-busy'); }
  }
  async function mutate(action, extra={}) {
    study=await api('/api/action/'+action,{id:study?.id,revision:study?.revision,...extra});
    draft=structuredClone(study.definition); dirty=false;
    if(study.analyses.length) analysisId=study.analyses.at(-1).id;
    history.replaceState(null,'','#study-'+study.id);
    await refreshShelf(); render();
  }
  function abandon() { return !dirty || window.confirm('草稿尚未保存。离开并放弃这些修改？'); }
  async function refreshShelf() {
    const result=await api('/api/studies');
    $('study-list').innerHTML=result.studies.length ? result.studies.map(s=>`<button class="study-item" data-open="${s.id}" aria-current="${s.id===study?.id}"><span class="cartridge-number">${esc(families[s.kind]?.split(' / ')[0])}</span><strong>${esc(s.title)}</strong><small>${esc(families[s.kind]?.split(' / ')[0] || s.kind)} · ${s.state==='draft'?'草稿':'已冻结'} · ${s.analyses} 次分析</small></button>`).join('') : '<p class="empty">还没有研究会话。</p>';
  }
  async function openStudy(id) { study=await api('/api/studies/'+id); draft=structuredClone(study.definition);dirty=false;analysisId=study.analyses.at(-1)?.id;tab=study.state==='draft'?'design':'evidence';sampleIndex=0;history.replaceState(null,'','#study-'+id);await refreshShelf();render(); }
  function options(values, selected) {return values.map(([value,label])=>`<option value="${esc(value)}"${String(value)===String(selected)?' selected':''}>${esc(label)}</option>`).join('');}
  function renderConditions() {
    const kind=draft.kind, frozen=study.state==='frozen';
    const policies=kind==='api-lab'?[['perfect','精确 oracle'],['uniform','均匀控制'],['wrong','错误控制']]:kind==='active-evidence'?[['stop','立即停止'],['checklist','固定检查表'],['myopic','一步 VOI'],['optimal','多步 oracle']]:[['oracle','oracle'],['wrong-field','字段错误'],['wrong-evidence','证据错误'],['wrong-version','版本错误'],['wrong-decision','决策错误']];
    $('conditions').innerHTML=draft.conditions.map((c,i)=>`<div class="condition" data-index="${i}"><strong title="${esc(c.id)}" aria-label="条件 ${esc(c.id)}">${String.fromCharCode(65+i)}</strong><label>条件名称<input data-field="label" value="${esc(c.label)}" required></label><label>原生路线<select data-field="route">${options([['decisions','Decisions'],['jev','Jev'],['openrouter-decisions','OpenRouter Decisions'],['clef','Clef'],['clef-flash','Clef Flash']],c.route)}</select></label><label>离线控制<select data-field="policy">${options(policies,c.policy)}</select></label><button type="button" data-remove="${i}" aria-label="移除条件 ${esc(c.id)}"${draft.conditions.length<=2||frozen?' disabled':''}>×</button><div class="condition-extra"><label>模型（留空使用该路线默认值）<input data-field="model" value="${esc(c.model||'')}" placeholder="默认模型"></label>${c.route.startsWith('clef')?`<label>Cloudflare account ID<input data-field="account_id" value="${esc(c.account_id||'')}" autocomplete="off"></label>`:''}${kind==='active-evidence'?`<label>材料开放方式<select data-field="query_mode">${options([['adaptive','逐轮按需核查'],['read-all','先读取全部材料']],c.query_mode||'adaptive')}</select></label>`:''}${kind==='typed-dag'?`<label>证据表示<select data-field="arm">${options([['direct','完整原文'],['fields-only','仅字段'],['source-linked','字段＋来源']],c.arm)}</select></label><label>Gold 干预<select data-field="intervention">${options([['','无'],['extraction','抽取'],['calculation','计算'],['retrieval','来源回查']],c.intervention||'')}</select></label>`:''}</div></div>`).join('');
    $('conditions').querySelectorAll('input,select').forEach(el=>el.disabled=frozen);
  }
  function readDraft() {
    const value=structuredClone(draft), form=$('design-form');
    for(const key of ['title','question','hypotheses']) value[key]=form.elements[key].value;
    value.replicates=Number(form.elements.replicates.value);
    document.querySelectorAll('.condition').forEach(row=>row.querySelectorAll('[data-field]').forEach(el=>{value.conditions[Number(row.dataset.index)][el.dataset.field]=el.value||null;}));
    if(value.schema_design)value.schema_design.fields=[...document.querySelectorAll('[data-schema-field]:checked')].map(el=>el.dataset.schemaField);
    return value;
  }
  function renderSchemaAudit(report) {
    const target=$('schema-audit-result');
    if(!report){target.innerHTML='<p class="local-note">选择需要保留的字段，再查找反例。搜索使用有限题本真值，不调用模型。</p>';return;}
    target.innerHTML=`<p class="schema-verdict">${report.insufficient_groups} / ${report.groups.length} 组仍缺少共同最优行动 · ${report.rows} 个有限世界</p><p class="local-note">相同字段不一定足以决定。以下结论仅覆盖当前合成题本；重复次数不增加独立世界。</p>`+report.groups.map((g,index)=>`<details${!g.sufficient&&index===report.groups.findIndex(item=>!item.sufficient)?' open':''}><summary>${esc(g.title||g.source_family)} · ${g.sufficient?'已有共同最优行动':'找到反例'}</summary><p>共同字段</p><pre>${esc(json(g.projection))}</pre>${g.sufficient?`<p>共同最优行动：${esc(g.common_optimal_actions.join(' / '))}</p>`:`<div class="schema-witnesses">${g.witness.map(w=>`<article><strong>${esc(w.id)}</strong><pre>${esc(w.source||json(w.values))}</pre><p>此世界的最优行动：<b>${esc(w.optimal_actions.join(' / '))}</b></p></article>`).join('')}</div><p>${g.minimal_repairs.length?'补入这些字段可区分本组：'+esc(g.minimal_repairs.map(r=>r.join(' + ')).join(' 或 ')):'当前可观察字段都不足以区分；需要新增可得证据，或保留不确定。'}</p>`}</details>`).join('');
  }
  function renderSchemaDesign() {
    const design=draft.schema_design;$('schema-design').hidden=!design;if(!design)return;
    const names={entity:'目标实体',status:'登记状态',current_version:'现行版本号',current_policy:'现行条款',archive_policy:'旧版条款'};
    $('schema-fields').innerHTML=Object.entries(names).map(([name,label])=>`<label><input type="checkbox" data-schema-field="${name}"${design.fields.includes(name)?' checked':''}${study.state==='frozen'?' disabled':''}>${label}<small>${name}</small></label>`).join('');
    const report=study.analyses.at(-1)?.result.conditions[study.definition.conditions[0].id]?.report.schema_audit;
    renderSchemaAudit(study.state==='frozen'?report:null);
  }
  function schemaTrace(row) {
    const e=row.schema_evidence;if(!e)return '';
    return `<section class="schema-trace"><h3>字段 → 核查 → 决定</h3><pre>${esc(json(e.projected_fields))}</pre><ol>${e.steps.map(s=>{const choice=s.chosen,observation=choice.observation?JSON.parse(choice.observation):null;return `<li><p>${s.compatible_hypotheses.length} 个世界仍相容 · 剩余预算 ${s.remaining_budget}</p><p>${s.common_optimal_actions.length?'共同最优行动：'+esc(s.common_optimal_actions.join(' / ')):'尚无共同最优行动'}</p><strong>${esc(choice.action||choice.failure)}</strong>${observation?`<blockquote>${esc(observation.quote)}</blockquote><small>${esc(observation.entity)} · v${esc(observation.version)} · ${observation.available?'来源可得':'来源缺失'} · ${esc(observation.locator.source)} [${observation.locator.start}, ${observation.locator.end})</small>`:''}</li>`;}).join('')}</ol><details><summary>本机复核原材料</summary><pre>${esc(e.source)}</pre><p class="local-note">${e.source_visible_to_model?'此条件已读取全部可得材料；完整原文进入模型终局请求，读取成本已计入。':'此条件的完整原文仅在本机检视；模型每轮看到投影字段、有限假设表与已经揭示的观察。'}</p></details></section>`;
  }
  function render() {
    $('welcome').hidden=!!study; $('study-view').hidden=!study;if(!study)return;
    $('study-kind').textContent=families[study.definition.kind];$('study-title').textContent=study.definition.title;
    $('research-question').textContent=study.definition.question;
    $('save-state').textContent=`${study.state==='draft'?'草稿':'设计已冻结'} · REV ${study.revision}`;
    const frozen=study.state==='frozen', form=$('design-form');
    for(const key of ['title','question','hypotheses','replicates']) { form.elements[key].value=draft[key]??'';form.elements[key].disabled=frozen; }
    renderConditions();renderSchemaDesign();$('definition-json').value=json(draft);$('definition-json').disabled=frozen;
    for(const id of ['save-design','freeze-design','add-condition','apply-json']) $(id).hidden=frozen;
    $('fork-study').hidden=!frozen;$('freeze-note').textContent=frozen?'设计已固定。派生新研究可以修改条件，旧证据仍保留。':'冻结保留任务、条件和解释器版本。';
    const count=draft.cases?.length || draft.suite?.cases?.length || draft.suite?.scenarios?.length || draft.schema_design?.families?.length;
    $('task-count').textContent=`${count??'—'} 个题目／机制 · ${draft.replicates} 次重复`;
    showTab(tab);renderEvidence();renderAnalysis();renderNotes();
  }
  function showTab(name){tab=name;document.querySelectorAll('[data-tab]').forEach(b=>b.setAttribute('aria-current',b.dataset.tab===name?'page':'false'));document.querySelectorAll('.tab-panel').forEach(p=>p.hidden=p.id!=='panel-'+name);}
  function selectedAnalysis(){return study?.analyses.find(a=>a.id===analysisId)||study?.analyses.at(-1);}
  function currentReport(key){return study.analyses.at(-1)?.result.conditions[key];}
  function latestRecord(key){return study.runs[key]?.at(-1)?.record;}
  function provenance(record){if(!record)return '尚无记录'; if(record.synthetic===true)return 'SYNTHETIC';if(record.provenance)return `${record.provenance} · synthetic=${fmt(record.synthetic)}`; const report=currentReport($('sample-condition').value)?.report;return report?.synthetic===true?'SYNTHETIC':'原生 workflow · 来源见各阶段';}
  function nativeRequests(record){return record?.manifest?.requests||record?.plan?.requests||[];}
  function nativeResponses(record,id,caseId){return record?.responses?.filter(r=>r.request_id===id)||record?.attempts?.filter(r=>r.request_id===id)||record?.results?.filter(r=>r.case_id===caseId)||[];}
  function samples(key){
    const record=latestRecord(key), evaluated=currentReport(key); if(!record||!evaluated)return [];
    if(study.definition.kind==='api-lab')return evaluated.ledger.trials.map(t=>({...t,id:t.request_id+'/'+t.question_id}));
    if(study.definition.kind==='active-evidence')return evaluated.report.episodes.map(t=>({...t,outcome:t.missing?'missing':t.failure_status||'ok',loss:t.total_loss,correct:t.wrong_commit?false:null}));
    return evaluated.report.rows.map(t=>({...t,outcome:t.terminal?t.decision_outcome:'missing',loss:t.terminal_loss}));
  }
  function renderEvidence(){
    const frozen=study.state==='frozen';$('run-controls').disabled=!frozen;
    $('run-controls-note').textContent=frozen?'运行各条件中选择的确定性控制，新增一次分析。不会发送任何 provider 请求。':'先保存并冻结设计，才会生成可运行的条件和完整 planned 分母。';
    $('run-conditions').innerHTML=frozen?study.definition.conditions.map(c=>{const run=study.runs[c.id].at(-1);return `<div class="run-row"><div><strong>${esc(c.label)}</strong><small>${esc(c.route)} · ${esc(c.model||'路线默认模型')}</small></div><span class="origin">${esc(run.origin)}<small>${study.runs[c.id].length-1} 次证据更新</small></span><button data-import="${c.id}">导入原生记录</button><button data-plan="${c.id}">下载当前请求 ↗</button></div>`;}).join(''):'';
    const previous=$('sample-condition').value;$('sample-condition').innerHTML=study.definition.conditions.map(c=>`<option value="${c.id}">${esc(c.label)}</option>`).join('');
    if(study.definition.conditions.some(c=>c.id===previous))$('sample-condition').value=previous;
    renderSamples();
  }
  function renderSamples(){
    const key=$('sample-condition').value, rows=samples(key), record=latestRecord(key);sampleIndex=Math.min(sampleIndex,Math.max(0,rows.length-1));
    $('sample-matrix').innerHTML=rows.map((r,i)=>`<button data-sample="${i}" class="${r.outcome==='missing'?'missing':r.outcome!=='ok'||r.correct===false?'bad':''}" aria-pressed="${i===sampleIndex}" aria-label="样本 ${i+1} ${esc(r.id)} ${esc(r.outcome)}">${i+1}</button>`).join('');
    const missing=rows.filter(r=>r.outcome==='missing').length;$('sample-count').textContent=`${rows.length} planned · ${missing} missing · ${provenance(record)}`;
    $('raw-record').textContent=record?json(record):'冻结后可检视保留记录。';
    if(!rows.length){$('sample-detail').innerHTML='<p class="empty">冻结设计后，全部 planned 样本会在这里出现。</p>';return;}
    const row=rows[sampleIndex];let request=null,response=null;
    if(study.definition.kind==='api-lab'){request=nativeRequests(record).find(r=>r.id===row.request_id);response=nativeResponses(record,row.request_id);}
    else if(study.definition.kind==='active-evidence'){
      request=(row.native_requests||[]).map(ref=>({round:ref.round,request:nativeRequests(record.rounds[ref.round]).find(r=>r.id===ref.request_id)}));
      response=(row.native_requests||[]).map(ref=>({round:ref.round,response:nativeResponses(record.rounds[ref.round],ref.request_id)}));
    }else {
      const stages=record.rounds.map(round=>({stage:round.stage,source:round.source,requests:round.plan.requests.filter(r=>(r.case_id===row.case_id||r.trial?.unit_id===row.case_id)&&r.trial?.replicate===row.replicate)}));
      request={projected_body:row.body,stages:stages.map(s=>({stage:s.stage,requests:s.requests}))};
      response=stages.map(s=>({stage:s.stage,provenance:s.source.provenance,synthetic:s.source.synthetic,responses:s.requests.flatMap(r=>nativeResponses(s.source,r.id,r.case_id))}));
    }
    $('sample-detail').innerHTML=`<span class="eyebrow">SAMPLE ${String(sampleIndex+1).padStart(2,'0')}</span><h3>${esc(row.id)}</h3><p class="outcome">${esc(row.outcome)} · loss ${esc(fmt(row.loss))} · correct ${esc(fmt(row.correct))}</p><button class="text-button" id="capture-example">把此样本带到笔记 ↗</button>${schemaTrace(row)}<details open><summary>答案与测量定义</summary><pre>${esc(json(row))}</pre></details><details><summary>保留请求 / rubric</summary><pre>${esc(json(request))}</pre></details><details><summary>原生回答 / 阶段记录</summary><pre>${esc(json(response))}</pre></details>`;
    $('capture-example').onclick=()=>{$('note-example').value=`${key} / ${row.id}`;showTab('notes');$('note-text').focus();};
  }
  function summary(key,evaluated){
    const r=evaluated.report,kind=study.definition.kind;
    if(kind==='api-lab'){
      const trials=evaluated.ledger.trials, losses=trials.filter(t=>t.outcome==='ok'&&t.loss!=null).map(t=>t.loss);
      const measures=[...new Set(trials.map(t=>t.measurement?.id || t.loss_kind || '见逐样本定义'))];
      const groups=new Map();for(const t of trials){const m=t.measurement||{id:t.loss_kind||'legacy loss',unit:'',semantics:''},k=json([m.id,m.unit,m.semantics]);if(!groups.has(k))groups.set(k,{...m,values:[],planned:0});const g=groups.get(k);g.planned++;if(t.outcome==='ok'&&t.loss!=null)g.values.push(t.loss);}
      const readings=[...groups.values()].map(g=>({...g,main:g.values.length?g.values.reduce((a,b)=>a+b,0)/g.values.length:null,n:g.values.length}));
      return {planned:r.coverage.expected_questions,missing:r.coverage.missing_question_slots,main:measures.length===1&&losses.length?losses.reduce((a,b)=>a+b,0)/losses.length:null,unit:measures.join(' / '),readings,rows:[['ok',r.coverage.ok],['unknown',r.coverage.unknown],['refusal',r.coverage.refusal],['error',r.coverage.error]],note:'各读数为对应测量中已定义且 ok 样本的均值；完整 planned 与失败代价见下方配对报告。'};
    }
    if(kind==='active-evidence')return {planned:r.summary.planned,missing:r.summary.missing,main:r.summary.prior_weighted_mean_total_loss,unit:'prior-weighted total loss',rows:[['查询成本',r.summary.query_cost],['业务暂缓',r.summary.abstained],['API failure',r.summary.api_failed],['模型调用',r.synthetic===true?0:r.native?.call_count],['输入 tokens',r.native?.usage?.input_tokens]],note:'主读数按 scenario prior 加权；配对报告另保留 family 等权与等 world 口径。'};
    return {planned:r.planned,missing:r.counts.missing,main:r.loss.total,unit:'terminal loss · total',rows:[['完整终局',r.counts.terminal],['正确决定',r.counts.correct],['与确定性 policy 一致',r.counts.honest_under_projection],['Gold 干预',r.gold_intervention||'无']],note:'policy 一致不代表诚实度或语义充分。原生来源与 gold 干预分开阅读；缺失使总损失保持未知。'};
  }
  function renderAnalysis(){
    const analysis=selectedAnalysis();$('analysis-select').innerHTML=study.analyses.map((a,i)=>`<option value="${a.id}"${a.id===analysis?.id?' selected':''}>${i+1} · ${esc(a.mode)} · ${esc(a.created_at.slice(11,19))} UTC</option>`).join('');
    for(const id of ['reproduce','reanalyse'])$(id).disabled=!analysis;
    if(!analysis){$('analysis-summary').innerHTML='<p class="empty">冻结设计后创建初始分析；未收到的回答保留为 missing。</p>';$('comparison-results').innerHTML='';$('interpreter-info').textContent='尚无评价版本';$('raw-analysis').textContent='';$('analysis-diff').innerHTML='';return;}
    $('analysis-summary').innerHTML='<div class="measure-grid">'+study.definition.conditions.map(c=>{const e=analysis.result.conditions[c.id],s=summary(c.id,e);return `<article class="measure"><h3>${esc(c.label)}</h3>${s.readings?s.readings.map(m=>`<div class="measure-reading"><span class="big">${esc(fmt(m.main))}</span><div><small>${esc(m.id)} · ${esc(m.unit)}</small><small>${m.n} observed / ${m.planned} planned</small></div></div>`).join(''):`<span class="big">${esc(fmt(s.main))}</span><small>${esc(s.unit)}</small>`}<p>${s.planned} planned · ${s.missing} missing · synthetic ${esc(fmt(e.report.synthetic))}</p>${s.rows.map(([label,value])=>`<div class="metric-line"><span>${esc(label)}</span><b>${esc(fmt(value))}</b></div>`).join('')}<p>${esc(s.note)}</p></article>`;}).join('')+'</div>';
    $('comparison-results').innerHTML=analysis.result.comparisons.map(c=>{const r=c.result;return `<section class="comparison"><h3>${esc(c.left.toUpperCase())} ↔ ${esc(c.right.toUpperCase())}</h3>${c.error?`<p>无法配对：${esc(c.error)}</p>`:`<p>${r.summary?.planned??r.planned??r.paired??r.pairs??r.rows?.length??'—'} planned / pairs · ${esc(r.metric||r.schema)}</p>${r.summary?.prior_weighted_scenario_equal?`<p>按 scenario prior 加权的平均总损失：${esc(fmt(r.summary.prior_weighted_scenario_equal.total_loss.left))} → ${esc(fmt(r.summary.prior_weighted_scenario_equal.total_loss.right))}　Δ ${esc(fmt(r.summary.prior_weighted_scenario_equal.total_loss.delta_right_minus_left))}</p>`:''}${r.by_measurement?.length?r.by_measurement.map(g=>`<div class="metric-line"><span>${esc(g.measurement.id)} · ${esc(g.measurement.unit)} · ${g.report.planned??g.report.paired} planned</span><b>${esc(fmt(g.report.estimate.left_loss))} → ${esc(fmt(g.report.estimate.right_loss))}　Δ ${esc(fmt(g.report.estimate.delta))}</b></div>`).join(''):r.estimate?`<p>配对单位平均 loss：${esc(fmt(r.estimate.left_loss))} → ${esc(fmt(r.estimate.right_loss))}　Δ ${esc(fmt(r.estimate.delta))}</p>`:''}${r.summary?.paired_delta_total!=null?`<p>完整配对终局损失：${esc(fmt(r.summary.left_loss_total))} → ${esc(fmt(r.summary.right_loss_total))}　Δ ${esc(fmt(r.summary.paired_delta_total))}</p>`:''}<details><summary>配对结果与统计口径</summary><pre>${esc(json(r))}</pre></details>`}</section>`;}).join('');
    $('interpreter-info').textContent=`${analysis.result.version} · ${analysis.interpreter.id.slice(0,16)}\n${analysis.mode} · ${analysis.created_at}${analysis.origin?' · '+analysis.origin:''}`;
    $('analysis-diff').innerHTML=analysis.diff?`<p class="local-note">与所选历史分析比较：${analysis.diff.equal?'结果一致':'存在变化'}${analysis.diff.truncated?'（差异最多展示100项）':''}</p>${!analysis.diff.equal?`<pre>${esc(json(analysis.diff.changes))}</pre>`:''}`:'';
    $('raw-analysis').textContent=json(analysis);
  }
  function renderNotes(){ $('notes-list').innerHTML=[...study.notes].reverse().map(n=>`<article class="note"><small>${esc(n.at)} · analysis ${esc(n.analysis?.slice(0,12)||'设计笔记')}</small><p>${esc(n.text)}</p>${n.counterexample?`<small>反例：${esc(n.counterexample)}</small>`:''}</article>`).join(''); }
  function download(raw,name){const url=URL.createObjectURL(new Blob([raw],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  function pick(consumer){fileConsumer=consumer;$('file-picker').value='';$('file-picker').click();}
  $('file-picker').onchange=()=>{const file=$('file-picker').files[0],consumer=fileConsumer;fileConsumer=null;if(file&&consumer)perform(async()=>{if(file.size>32*1024*1024)throw new Error('文件超过32 MiB');await consumer(await file.text());},'导入已保存；来源声明仍与实采认证分开。');};
  document.addEventListener('click',event=>{const b=event.target.closest('button');if(!b||b.disabled||!b.closest('.studio'))return;
    if(b.dataset.create&&abandon())perform(async()=>{tab='design';await mutate('create',{kind:b.dataset.create});});
    if(b.dataset.open&&abandon())perform(()=>openStudy(b.dataset.open),'已打开研究');
    if(b.dataset.tab)showTab(b.dataset.tab);
    if(b.dataset.remove){draft=readDraft();draft.conditions.splice(Number(b.dataset.remove),1);dirty=true;renderConditions();}
    if(b.dataset.sample){sampleIndex=Number(b.dataset.sample);renderSamples();}
    if(b.dataset.import)pick(record_json=>mutate('import-record',{condition:b.dataset.import,record_json}));
    if(b.dataset.plan)perform(async()=>{const plan=await api(`/api/studies/${study.id}/plan/${b.dataset.plan}`,undefined,true);if(plan.trim()==='null')throw new Error('此条件已终局，没有下一轮请求。');download(plan,`${study.id}-${b.dataset.plan}-plan.json`);},'当前原生请求已下载；发送仍使用已有 CLI 和显式预算。');
  });
  $('new-study').onclick=()=>{if(!abandon())return;study=null;draft=null;dirty=false;history.replaceState(null,'','#research-studio');render();refreshShelf().catch(e=>notice(e.message,true));};
  $('audit-schema').onclick=()=>perform(async()=>{draft=readDraft();renderSchemaAudit(await api('/api/action/audit-schema',{design:draft.schema_design}));},'有限世界搜索完成；没有 provider 调用。');
  $('schema-fields').addEventListener('change',()=>{draft=readDraft();dirty=true;renderSchemaAudit(null);});
  $('design-form').addEventListener('input',()=>{dirty=true;$('save-state').textContent='草稿有未保存修改';});
  $('conditions').addEventListener('change',()=>{draft=readDraft();dirty=true;renderConditions();});
  $('add-condition').onclick=()=>{draft=readDraft();if(draft.conditions.length>=8)return notice('最多8个条件',true);const id='abcdefgh'.split('').find(x=>!draft.conditions.some(c=>c.id===x));draft.conditions.push({...draft.conditions.at(-1),id,label:'新条件'});dirty=true;renderConditions();};
  $('apply-json').onclick=()=>{try{const parsed=JSON.parse($('definition-json').value);if(parsed.kind!==draft.kind||!Array.isArray(parsed.conditions))throw new Error('保留研究 family，并提供 conditions 列表');draft=parsed;render();dirty=true;notice('JSON 已应用到草稿；保存时执行完整校验。');}catch(e){notice(e.message,true);}};
  $('design-form').onsubmit=e=>{e.preventDefault();perform(()=>mutate('save',{definition:readDraft()}));};
  $('freeze-design').onclick=()=>perform(async()=>{await mutate('save',{definition:readDraft()});await mutate('freeze');},'设计已冻结；全部 planned 样本已保留。');
  $('fork-study').onclick=()=>perform(async()=>{tab='design';await mutate('fork');},'已派生新研究，原研究保留。');
  $('run-controls').onclick=()=>perform(async()=>{await mutate('run');showTab('analysis');},'离线对照完成；没有 provider 调用。');
  $('sample-condition').onchange=()=>{sampleIndex=0;renderSamples();};
  $('analysis-select').onchange=()=>{analysisId=$('analysis-select').value;renderAnalysis();};
  $('reproduce').onclick=()=>perform(()=>mutate('reproduce',{analysis:selectedAnalysis().id}),'保留解释器复现已完成，差异已保存。');
  $('reanalyse').onclick=()=>perform(()=>mutate('reanalyse',{analysis:selectedAnalysis().id}),'当前版本重分析已保存，旧评价保持原样。');
  $('export-study').onclick=()=>perform(async()=>download(await api(`/api/studies/${study.id}/export`,undefined,true),`study-${study.id}.json`),'研究包已导出。分享前请检查是否含私人输入；包内不含可执行程序。');
  $('import-bundle').onclick=()=>{if(abandon())pick(bundle_json=>mutate('import-bundle',{bundle_json}));};
  $('note-form').onsubmit=event=>{event.preventDefault();perform(async()=>{await mutate('note',{text:$('note-text').value,counterexample:$('note-example').value,analysis:selectedAnalysis()?.id||null});$('note-text').value='';$('note-example').value='';},'研究笔记已保存，并绑定当次分析。');};
  window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
  (async()=>{await refreshShelf();if(/^#study-[a-f0-9]{32}$/.test(location.hash)){await openStudy(location.hash.slice(7));$('research-studio').scrollIntoView();}})().catch(e=>notice(e.message,true));
})();
