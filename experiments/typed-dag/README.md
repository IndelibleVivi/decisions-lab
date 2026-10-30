# Typed DAG：抽取、计算与决定之间的证据

本实验把原文 → Clairic 类型化抽取 → Decimal 计算 → 原生 decision 变成可保存和回放的依赖链。它研究字段抽取是否保留了决定所需的信息，并通过 gold-stage 干预定位失败发生在哪一层。原生记录继续由 typed-values、api-lab 与 collector 拥有；本模块只保存任务、阶段关联和工作流评价，不新增 transport。

本题本的[首轮模型实验](pilot-2026-10-30.md)固定 Clairic＋官方 Luna、8 个条件与两次重复；设计、实采状态与汇总独立保留。synthetic demo 验证依赖与测量路径，不提供模型收益或生产效果结论。

当前题本为 **7 cases／6 source families**：完整数值、同名异实体、现行版本更正、缺失操作数、schema-gap 配对、证据链接修复。它使用固定的 1,200 CNY 采购规则与明确的「目标现行状态」文本约定；可以在该有限契约中增加 cases，不是任意业务规则的通用 DAG engine。改变规则须修改并验证 evaluator，不能只改 suite 文案。

## 三条路径与阶段干预

同一个原创任务比较完整原文直接判断、仅字段与计算结果判断、字段与实际证据链接判断。抽取值必须真实进入后续输入；后续请求在取得第一阶段响应以后生成，不能预先把编辑答案填入请求。

```text
原文 ──────────────────────────────────→ direct 判断
  └→ Clairic 原生字段 → Decimal 计算 ────→ fields-only 判断
                    └→ 关联原文证据 ────→ source-linked 判断
各路径的原生回答 → 完整 planned 分母、终局损失、阶段诊断
```

字段正确率和终局损失分别报告。存在这样的配对：数量、单价、运费等 gold fields 完全相同，但原文中的适用条件不同，完整任务的最优动作不相交。这时字段版失败可能来自 schema 信息不足；不能归因于提取器把数字读错。fields-only 保持自己的严格状态文本 policy；来源绑定只约束 source-linked，不能把两种充分性检查混成一项。

gold extraction 替换抽取结果，gold calculation 采用编辑定义的完整操作数与计算中间值，gold evidence retrieval 替换证据选择。每种干预保留替换的值与来源；gold-derived 路径不能记成完整 live 工作流。比较是条件性诊断，阶段交互不假定为可相加的因果贡献。

普通 source-linked 只带实际抽取并核对通过的原文摘录，不自动补齐 schema 没有抽出的状态。新建 workflow 的 `projection_revision` 为 `2`：摘录必须是 task source 中唯一的逐字片段，位于唯一且带「目标现行状态：」标签的行内；提取出的 `target_entity` 与 `target_version` 也必须和同一份原文的唯一「目标记录：」一致。错误实体、旧版、歧义重复、改写或捏造片段不进入下游；source-linked 的字段区也不再旁路暴露未经绑定的状态摘录。校验结果在报告的 `retrieval.verification` 中给出 `bound`／`rejected` 状态和原因；绑定成功时，下游 body 写入精确 quote 的 Unicode codepoint 半开 locator。它不冒充 Clairic span 约定已实测。gold 来源保留在 workflow/report；provider body 不带 oracle、正确性、gold 或内部 gold 原因标记。

当前完整离线控制：direct 7/7、fields-only 5/7、普通 source-linked 5/7；后两者终局损失各 4，gold retrieval 后 source-linked 恢复 7/7、损失 0。两次缺失正来自 schema-gap 配对。这里的决定由只读 body 的确定性 policy 生成，是检查测量能否暴露信息损失的控制结果，不是模型成绩。

## 运行与阶段衔接

在 repo 根目录使用 Python 3.11+。默认完全离线，输出只能保存到 `runs/` 或 repo 外的新路径。

```bash
python3 -m decision_lab research typed-dag-suite --output runs/typed-dag/suite.json
python3 -m decision_lab research typed-dag-demo --suite runs/typed-dag/suite.json --route decisions --output runs/typed-dag/demo.json
python3 -m decision_lab research typed-dag-report runs/typed-dag/demo.json

python3 -m decision_lab research typed-dag-start --suite runs/typed-dag/suite.json --route decisions --output runs/typed-dag/state-0.json
python3 -m decision_lab research typed-dag-prepare runs/typed-dag/state-0.json --output runs/typed-dag/stage-0.json
```

每份 workflow 固定一个 `--condition`，默认 `fields-only`。`direct` 直接准备 api-lab；`fields-only` 与 `source-linked` 先准备原生 typed-values，取得抽取响应后才准备 api-lab。`--intervention extraction` 使用明确标记的 gold fields 并跳过抽取调用；`calculation` 替换计算，`retrieval` 仅适用于 `source-linked`。direct 不接受 gold-stage 干预。

prepare 导出本阶段 retained collection plan，继续使用现有导入与 collector 路径。取得本阶段原生 record 或 collection 后（collection 可传 run 目录或 `collection.json`）：

```bash
python3 -m decision_lab research typed-dag-apply runs/typed-dag/state-0.json <本阶段记录路径> --output runs/typed-dag/state-1.json
python3 -m decision_lab research typed-dag-prepare runs/typed-dag/state-1.json --output runs/typed-dag/stage-1.json
python3 -m decision_lab research typed-dag-report runs/typed-dag/state-1.json
```

三条路径分别保存后可以配对比较：

```bash
python3 -m decision_lab research typed-dag-demo --condition direct --output runs/typed-dag/direct.json
python3 -m decision_lab research typed-dag-demo --condition source-linked --intervention retrieval --output runs/typed-dag/gold-retrieval.json
python3 -m decision_lab research typed-dag-compare runs/typed-dag/demo.json runs/typed-dag/gold-retrieval.json
```

`typed-dag-demo --policy` 另支持 `wrong-field`、`wrong-evidence`、`wrong-version`、`wrong-decision`，用于检查错误传播及归因；默认 `oracle` 指 body-only 的确定性控制，字段本身仍来自明确 synthetic fixture。计算报告分别显示采用操作数是否完整、Decimal 算术一致性、总额是否匹配 gold，以及原生 `computed_total` 与代码结果是否相同。上游字段错不会被记成代码算错。`projection_revision: 2` 的普通与 gold calculation 都把等值 Decimal 归一为同一个无指数、无损的确定文本（例如 `300.00`、`300.` 与 `300` 均为 `300`）；原始 extraction 仍原样保留，模型 `computed_total` 不替代代码计算。

以上仍是 synthetic fixture，不产生 provider 请求。真实采集将 prepare 的 plan 交给 `research collect`，见[环境凭据与阶段预算](../../docs/research-infrastructure.md#有预算的采集与恢复)；Clairic 需要本次 `CLOUDFLARE_ACCOUNT_ID` 与 token，decision 则使用 workflow 固定 route 的凭据。重复调用的身份优先保存在 retained collection；不把无重复身份的旧 record 猜配到多个 replicate。

全部完成后 prepare 返回 `null`。每次 apply 保存新快照，不覆盖原始响应；旧阶段或不匹配的 body 不能应用。真实调用仍需明确本次模型、输入、凭据和全程上限；本说明不授权调用，collector 的单阶段限额不能冒充全程账单上限。

缺少 `projection_revision` 的旧 workflow 按 revision 1 重放：继续使用原严格前缀 quote 与旧 Decimal 文本，不会因新 evaluator 静默改变历史保留记录。需要修正语义的新 workflow 由 `typed-dag-start`／`typed-dag-demo` 明确写入 revision 2；v1 与 v2 的 stage plan 因计算和 evidence payload 不同，不能用旧 plan 冒充新 plan。

## 解释与边界

- 原生 scalar null 保持缺失，不用 guess 填回；缺 field、错误类型和无有效响应分别处理。
- 抽取、确定性计算、证据与 decision 各保留自己的实际输入和来源；没有模型回答时不以 baseline 补成 native 成绩。
- 同实体、当前版本和证据支持关系需要独立检查；字符串在原文出现不证明其适用。revision 2 的 `retrieval.verification` 只说明本地绑定规则通过，不证明模型回答为真，也不把 `matches_gold` 发给 provider。
- 历史 pilot 的普通 quote 仍按当时冻结的严格前缀解释；本修订不重跑、不改写原始记录或把修正后的离线控制当成新的 live 结果。v1 可准确 replay，新的短摘录行为只属于显式 revision 2。
- 正常答案、业务补材料、API unknown/refusal/error 和 planned missing 分开。任一阶段缺失都保留终局分母，已发生的请求与成本不消失。
- usage、latency 和费用按 stage/request 归属一次，完整明细可以回看。同 suite／replicates 的字段与来源路径共享相同 extraction plan，可以应用同一 retained collection；比较显示共享上游 request 数，两侧成本不能再相加。任一实际 request 的对应计量未知时，总额保持 null；synthetic call count 为 0，imported calls 未知。
- 未完成的 planned rows 保持 missing，完整 loss total 和 paired delta 不伪造数值；已观察 pairs 的条件汇总另列分母。完成的 API failure 保留设计 failure loss 12，并与正常业务补材料分开。
- 本地 oracle、fixture 与 gold-stage 干预是 synthetic 控制。字段与终局都正确，也不能据此外推真实材料、总体校准或生产采用。

原有[三组 typed-values 题本](../typed-values/README.md)及其 NOT_RUN authoring 快照继续保留；它们的三路径 baseline 不被倒写成这里的实际串行模型实验。持续研究目标见[研究主线](../../docs/research-programme.md)。
