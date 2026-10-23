# API 能力实验 · 规则、概率与视觉判据

独立且默认离线的实验族：研究原生 Decisions API 能表示什么、返回对象怎样解释、干预会改变什么。依据见 [10-22 核查](../../research/2026-10-22/README.md)，完整七方向见[能力方法章](../../docs/api-capabilities.md)。

**状态：题本、请求准备、synthetic demo、本地响应导入、版本化评分与 replay 已实现。** 题本文件保留 `provider_status=NOT_RUN` 的 authoring 状态；[首轮 provider 实验](../provider-pilot/README.md)独立记录后续真实采集、失败和固定 subset，不自动改写旧题本。默认离线命令不读取凭据、不发送模型请求；显式开启的 collector 见[研究基础设施](../../docs/research-infrastructure.md)，不执行生成代码或外部动作；有界函数由本地代码查表评分。每条新请求携带 `trial.unit_id/source_family/condition/replicate/split/seed`；原生 body 不含这些编辑身份。重复先逐次评分再聚合，未标明的逻辑重复拒绝，不能覆盖。旧 manifest 只读兼容，历史 model 不受当前默认值改变影响。旧 [next-action](../next-action/README.md) 和 [typed-values](../typed-values/README.md) 契约独立。

## 题本与预算

| 实验 | 原创材料与干预 | 完整单 route 预算 |
| --- | --- | --- |
| `rule-compile` | 24 条自然语言完整规则覆盖 16 个函数；前 8 个函数另有否定和变量名改写。比较一次编译、四状态打包；编译另有倒序和不透明 ID；加 1 条欠说明规则 | 97 请求／169 题；基本结构 48 请求／120 题，干预与欠说明另计 |
| `probability` | 两个边缘相同而联合相反的世界，加一个质量拆分世界；每个世界有 5 道数值题的单问与打包、joint Choice、粗／细菜单 | 27 请求／39 题 |
| `visual-criteria` | 24 个目标，contains／touching／disjoint 各 8，分别使用文字、图片、文字加图片、交换图片定义 4 条件 | 96 请求／96 题；仅 Jev |

完整 OpenAI 题本为 124 请求／208 题，Jev 为 220 请求／304 题。**完整题本预算不表示已发生完整采集；日期实验可能只选择明确的 subset。** 同一 run 可用 `prepare/demo --replicates N` 保留显式重复，独立采集仍使用新 run；token、缓存、费用与延迟按具体运行观测，不从问题数推算。

`api_tasks.py` 拥有生成规则，`suite.json` 拥有版本入口，`api_lab.py` 拥有协议与记录。相同 suite schema 也接受自定义 `cases` 数组，每例包含 `id/experiment/input/questions/rubric`，无需改 next-action 动作常量。支持 Choice、Predicate／Noul、Score，不宣称覆盖供应商全部输入 schema。

## 跑通离线路径

Python 3.11+、标准库即可；在 repo 根目录运行：

```bash
python3 -m decision_lab api-lab list
python3 -m decision_lab api-lab validate
python3 -m decision_lab api-lab prepare --experiment rule-compile --route decisions --limit 1
python3 -m decision_lab api-lab demo --experiment probability --route decisions --run-dir runs/api-prob-001
python3 -m decision_lab api-lab report runs/api-prob-001
python3 -m decision_lab api-lab replay runs/api-prob-001
python3 -m decision_lab api-lab demo --experiment visual-criteria --route jev --limit 4 --run-dir runs/api-vision-001
```

`--case-id` 可重复，`--limit` 限制请求 case 数，不自动补齐干预。视觉前 4 例是同一目标的 4 条件。默认模型是 `gpt-6-luna`／`jev-1.14.0`；`--model` 保留明确指定值，returned model 另列。名称存在不证明服务端接受。

### 新原生路线

| `--route` | 模型选择与传输 | 当前输入范围 |
| --- | --- | --- |
| `clef` / `clef-flash` | Body 固定为 `clef` / `clef-flash`，URL 使用对应 `@cf/cloudflare/…`；准备时显式传 `--account-id` | 文本、多题 Choice／Noul／Score |
| `openrouter-decisions` | 原生 `/api/alpha/decisions`；默认 `baseten/mammoth-1:free`，`--model` 可明确选付费模型或已识别的免费 ID | 文本、多题 Choice／Noul／Score |

当前识别的免费 ID 为 `inception/mercury-decide:free`、`baseten/mammoth-1:free`、`baseten/elephant-1:free`、`respan/span-01-lite:free`。首轮采集后，默认免费模型选择本轮实际可调用的 Mammoth；Mercury 保留为显式候选，本轮被原隐私政策阻断。免费标记、当日目录和实际可调用分开；账户 ZDR／训练政策、provider 限制或额度可能使请求失败。未知免费 ID 先拒绝，更新支持时核对官方目录；不把不存在的免费名称改成付费模型。显式付费模型仍需独立的调用与预算授权，collector 的输入估算不是金额上限。

```bash
python3 -m decision_lab api-lab prepare --experiment probability --route clef --account-id "$CLOUDFLARE_ACCOUNT_ID" --limit 1
python3 -m decision_lab api-lab prepare --experiment probability --route openrouter-decisions --model baseten/mammoth-1:free --limit 1
```

这些命令只准备请求。CF 账号被保留在本地 manifest 的 endpoint 中，不把真实 manifest 发到公共仓库。CF REST 外层成功、模型身份与逐题答案分别校验；Score 的原生 scalar 与分布均值分别保存，不强制用均值替换答案。新路线没有接通图片 criteria；视觉题仍只走 Jev 原生 assets 契约。

prepare 输出 **本地 manifest**，其中 `requests[].body` 与 `required_headers` 是原生请求部分，其余包含本地 rubric、身份与摘要。**不能把整个 manifest 发给模型。** 编辑答案、真值与运营 ID 留在 body 外。OpenAI 当前实验 profile 只准备文本；Jev 图片 criteria 使用自己的 assets 契约。

## 三组评分的区别

规则输入是自然语言，不直接给出真值表；候选描述列出有界函数，状态顺序固定 `00,01,10,11`。代码只查表，不使用 `eval`。报告完整函数正确性、Hamming 错误和具体反例状态；顺序／ID／改写一致性与正确率分开。缺配对不算稳定。仅给 A 为必要条件仍容许 4 个函数，`insufficient` 是正常可正确评分的 `ok`，不是 refusal。

概率实验分开保存世界的事件概率、模型选中的数值答案、原生候选质量和 confidence。旧 10-22 manifest 与默认题本保留原 27/39；独立 `research partition-events --route decisions` 新增 3 requests/12 questions，逐题定义 A/A1/A2/区域B 对应的状态集合，用数值答案检验区域加法，不从众数菜单概率代替推断。单问／打包保持逐字相同的 5 道问题与 input；报告真值误差、交集界、并／异或恒等式及组织方式差异。粗菜单 `A=(10∨11), B=(00∨01)` 与细菜单 `A1=10, A2=11, B=(00∨01)` 互斥穷尽。质量漂移直接从原生分布计算，joint Choice 的投影另标候选质量测量。demo 有意构造粗质量 0.60、细质量 0.75 的 −0.15 反例；它只证明可以测量答案菜单质量漂移，不证明事件概率错误。完美 one-hot oracle 也可能每题答对且 mass delta=1；使用 `research oracle` 的三种控制区分答案正确性、数值事件误差和菜单敏感性。缺失和拒答不补为概率 0，自洽不保证准确。

视觉图片来自原创坐标规则，均为 320×320 PNG。包含、只在边界接触、有间隔分离互斥；变体改变位置、尺寸、颜色、背景。绘制与真值使用同一坐标，测试还解码像素核对。四条件在 state 始终引用同一目标图；图片条件与 `swapped-image` 的 state、问题、K 标签和顺序相同，只轮换 criteria 参考图，真值同步改变。asset key 不含关系名。报告标签翻转与两次都跟随定义的正确性，单纯翻转不算理解。

Jev 顶层 assets 由 state／criteria 引用，需 `TypeSafe-Danger-Zone-Images: true`；图片能力仍为实验状态。此 profile 检查引用、PNG、280–1568 px 边长和单图大小，不完整复刻服务端展开体积、压缩或质量限制。run 的 `evidence/<request-id>/` 可查看当次目标和参考 PNG。

## 导入本地原生响应

保存准备时的同一份 manifest，不在导入时重造旧请求：

```bash
mkdir -p runs/api-inputs
python3 -m decision_lab api-lab prepare --experiment probability --route decisions --case-id prob-correlated-single-a > runs/api-inputs/manifest.json
python3 -m decision_lab api-lab validate --manifest runs/api-inputs/manifest.json
python3 -m decision_lab api-lab import --manifest runs/api-inputs/manifest.json --responses experiments/api-capabilities/example-responses.json --run-dir runs/api-import-001
python3 -m decision_lab api-lab replay runs/api-import-001
```

[example-responses.json](example-responses.json)是明确标注的 **synthetic 原生形状 fixture**。envelope 形式为：

```json
{
  "schema": "decisions-lab.api-responses/1",
  "synthetic": true,
  "responses": [
    {
      "request_id": "prob-correlated-single-a",
      "http_status": 200,
      "response": {"model": "gpt-6-luna", "answers": []}
    }
  ]
}
```

上面的空 answers 只展示 envelope，实际示例文件有完整分布。每个 request ID 对应一个准备请求，可附实际 `latency_ms/usage/cost`；未观测就省略或 null，HTTP 状态也不自动补 200。传输失败可用 `error` 字符串，HTTP 失败保留 status 与原始 body。

synthetic 是输入来源声明，可为 true、false、或省略表示未知，不证明 provider 真实性。import provenance 始终是 `imported`，live_verified 始终 false；导入 synthetic 示例仍保留 synthetic 标记。

默认要求全覆盖；`--allow-partial` 明确允许部分导入，报告以完整 manifest 的请求／题数为分母。重复／外来 request ID、重复 JSON key、非有限值拒绝。每题的缺失、refusal、解析错误独立记录，能对齐的其他答案保留；外来答案另列 request contract issue。Jev 没有文档支持的 refusal 形状，不能凭空添加。

## 快照、重放与第二版 rubric

新 run 的 `record.json` 保存当时的原生请求、非秘密 header、本地 rubric、raw response、来源与摘要；独立 `evaluation.json` 保存 evaluator/rubric 版本、coverage、类型化结果、指标与反例。synthetic run 另导出可离线导入的 manifest 与 responses。

replay 从 raw response 重算，不信任 evaluation 缓存，不调用当前生成器或默认模型重造请求。修改保留的请求、响应或来源会触发摘要不匹配；摘要保留 JSON 对象顺序，覆盖 Jev criteria 排列变化。摘要仅核对本地完整性，不是 provider 签名或 live 采集证明。

当前 evaluator 为 `api-capabilities/3`：沿用 `/2` 的逐 replicate 事件装配、误差与 coherence；菜单质量仅作描述。`/3` 只对 OpenRouter 应用其[官方 SDK 声明的两位小数舍入](https://github.com/OpenRouterTeam/ai-sdk-provider#evaluation)：完整、有限、范围合法的菜单若总和偏离 1，必须落在 0.01 网格，且每项舍入区间相加可包含 1。保留返回概率、总和和精度区间，**不重新归一化**；CF、直连 Jev 与 OpenAI 的总和检查保持严格。原生 Score 与返回菜单的加权均值分别保存，不强迫相等。manifest/record 的 `/1` 仍只读兼容，历史已保存评价不被覆写；从同一 raw 重算时保留旧评价，并标明新 evaluator/rubric 版本，不冒充当时已产生的分析。

```bash
python3 -m decision_lab api-lab report runs/api-import-001 --rubric runs/api-inputs/rubric-v2.json --output runs/api-import-001/evaluation-v2.json
```

rubric 文件为 `{"version":"editorial-v2","requests":{"<request-id>": <完整替代rubric>}}`，结构参考 manifest，真值须匹配原生候选／类型。新评价与旧结果并存，不改推理文件。修订标签要有依据，不能为了得分改变数学真值。所有输出使用新路径；repo 内只允许写入忽略的 `runs/`。

```bash
python3 -m unittest tests.test_api_lab
python3 tools/check.py --core-only
```

## 限制

Choice 检查完整分布、typed value、候选／argmax 与 confidence 范围；Score 分布、数值 score 和分布均值分别保留，不用统一公式替换 provider confidence。不完整验证 context token 预算、缓存命中、全部原生输入、区域或账号支持。其余语义特征、语义寻址、Clairic list/forecast、时间和音视频仍为[研究设计](../../docs/api-capabilities.md)。真实采集还需 provider、输入边界、重复数与调用上限授权，离线通过不证明模型能力、价格、校准或生产效果。
