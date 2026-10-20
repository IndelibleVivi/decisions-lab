# Typed values：三组可核对的实验

[字段方法](../../docs/typed-values.md) · [原创请求与编辑答案](examples.json) · [10-20 契约核查](../../research/2026-10-20/README.md)

**状态：NOT_RUN。** 本目录提供实验设计与原创合成材料：3 组实验、7 个请求案例，尚无模型响应。`examples.json` 中的 `editorial_oracle` 是编辑依据输入写出的预期答案，第三组另有原创的事后观测；`provider_results` 为空。下面的确定性计算只验证这些教学材料，没有测得模型质量。

请求草案采用 Clairic 的原生 `model`、`state`、`fields` 形状，字段依据 [2026-10-20 核查](../../research/2026-10-20/README.md)及[固定版本的官方 schema](https://github.com/cloudflare/cloudflare-docs/blob/39cb53c8e8aa663096c589831bcecd1e5d657641/src/content/workers-ai-models/clairic.json)。本目录不提供 collector；原有 `decision_lab` CLI 仍使用 [next-action 契约](../next-action/README.md)，不接受这份 JSON。

## 资料怎么使用

每个案例有一个完整的 `request` 对象。只有这个对象是拟发送的原生请求体；`id`、`source_group`、编辑答案、诊断样例及实验设计都留在请求之外。模型路径为 `@cf/cloudflare/clairic`，请求体的 `model` 为 `clairic`。字段语义与服务端能力以官方来源为准，本文的任务和评分规则由本项目定义。

可以先在仓库根目录离线打印第一个请求，逐字段检查：

```bash
python3 - <<'PY'
import json
from pathlib import Path
data = json.loads(Path('experiments/typed-values/examples.json').read_text())
case = data['experiments'][0]['cases'][0]
print(json.dumps(case['request'], ensure_ascii=False, indent=2))
PY
```

这条命令只读本地 JSON。未来真实运行应另行记录所选模型、时间、完整出站请求、原始响应、截断信息与 usage；按现有仓库约定显式选择网络和调用上限。7 个案例是教学种子，同组变体共享材料，不能算作 7 个独立评测样本。

## 实验一：缺失值与来源归属

### 要回答的问题

当输入同时包含两个实体，模型能否保留当前实体的缺失值？程序是否会把一个确实存在的字符串误认为正确答案？

### 原创输入与请求

`examples.json` → `source-null-identity` → `source-missing` 的完整输入是：

```text
资料版本 v2（2026-10-20）。当前订单 PO-842：收件人为林遥；没有列出交付日期。归档订单 PO-497：收件人为周岚；交付日期为 2026-10-18。
```

原生请求要求四个字段。以下是与 JSON 资料一致的定义；完整 `state` 在同一案例的 `request` 中：

```json
{
  "current_order_id": {
    "type": "text",
    "instructions": "逐字摘录当前订单的订单号；不取归档订单。"
  },
  "current_recipient": {
    "type": "text",
    "instructions": "逐字摘录当前订单 PO-842 的收件人姓名；不取归档订单。"
  },
  "current_delivery_date": {
    "type": "date",
    "instructions": "当前订单 PO-842 的交付日期。原文没有给出时返回 null，不取其他订单的日期。"
  },
  "current_delivery_evidence": {
    "type": "text",
    "instructions": "逐字摘录原文明确给出的当前订单 PO-842 的交付日期；原文未给出日期时返回 null。"
  }
}
```

请求另设 `options.return_state_text: true`，便于后续核对实际文本。`current_delivery_date` 是标准日期字段，`current_delivery_evidence` 则保留日期在原文中的文字；两者的用途不同。

### 编辑答案与诱惑性错误

| 字段 | 编辑预期值 | 理由 |
| --- | --- | --- |
| `current_order_id` | `PO-842` | 目标是当前订单 |
| `current_recipient` | `林遥` | 姓名属于 PO-842 |
| `current_delivery_date` | null | 当前订单没有给出日期 |
| `current_delivery_evidence` | null | 当前订单没有可摘录的日期文字 |

资料另列两个**人为构造的坏候选**：`周岚` 和 `2026-10-18`。它们都能在原文找到，却属于归档订单。这不是模型发生过的错误，而是将来验证评分器能否识别的反例。

Clairic 官方示例中，null 字段仍可能带有 `guess` 和 span；我们读取字段值时不得用 guess 补空。[模型示例与含义](../../research/2026-10-20/README.md) 若未来返回 `value: null`，记录应保留 null；若缺少整个字段，则是响应契约问题，不能伪装成正确识别缺失。

### 确定性 baseline

对这个明确模板，先按“当前订单 PO-842”到“归档订单”之间的文本划定目标范围，再提取订单号、`收件人为…；` 和该范围内的 ISO 日期。没有日期就返回 null。这个 baseline 已足以解决教学输入；它的模板依赖应与结果一起展示，不能外推到任意合同或扫描件。

对 text 值先检查它是否逐字出现在目标范围。自动数值 span 校验单独列为待验证项：本轮官方来源没有建立位置的编码单位及端点约定。不能先假定 Python 切片或 JavaScript substring 的结果就是 provider 定义。

### 控制变量

| 案例 | 唯一改变 | 编辑预期 |
| --- | --- | --- |
| `source-missing` | 基准材料 | 当前日期为 null |
| `source-present` | 把“没有列出交付日期”改成“交付日期为 2026-10-23” | 当前日期变为 2026-10-23，归档日期仍不能采用 |
| `source-unicode-prefix` | 在 present 输入前加 emoji、预组合字符及组合字符前缀 | 字段语义不变；位置应对应新输入 |

Unicode 前缀同时包含 `é` 和 `e` 加 combining acute。保留实际字符串，不在发送或评估时偷偷规范化。待有真实响应，分别按 UTF-8、code point、UTF-16 和不同端点假设核对，直到能用明确证据确定约定；遇到不能唯一解释的结果，记录为 `span_convention_unresolved`。

### 指标与失败判据

记录尝试次数、正常返回次数和失败次数，再分别统计字段值精确匹配、存在字段漏提率、缺失字段误填率、错误实体归属率。定位正确与语义正确分列；未核定 offset 约定时，不报告“span 校验通过”。

以下任一情况都应在案例级报告失败：用归档订单的日期填当前日期；将 null 的 guess 当作有效值；字段缺失被记成 null 成功；Unicode 前缀造成字段值改变；或定位只能通过偷偷修改输入得到一致。预测为 null 也可能漏掉本来存在的值，因此 present 变体与 missing 变体必须一起看。

## 实验二：算对金额以后该做什么

### 要回答的问题

提取数字并让代码算术，是否就足以给出正确下一步建议？当投影丢掉争议信息，下游怎样诚实地承认材料不够？

### 原创输入与原生请求

`extract-compute-decide` → `amount-disputed`：

```text
任务规则：只有金额不超过 1200.00 CNY 且交付无未解决争议时，才建议继续处理；存在未解决争议时建议先核对争议；缺少必要事实时建议补材料。
采购单 PO-731，版本 v2。数量 3 件；单价 350.00 CNY；运费 50.00 CNY。金额按数量乘单价再加运费计算，不含其他费用。
版本 v2 的验收状态：第三件尚未验收；供应商所称全部已交付已被仓库纠正，争议未解决。
```

完整 Clairic 请求在该案例的 `request`。它分别要求 `quantity`、`unit_price`、`shipping` 三个 number 字段、模型计算的 `computed_total`，以及逐字保留整句验收状态的 `status_evidence`。数值字段明确精度和单位，text 字段保留语义条件；`options.return_state_text` 为 true。

编辑答案为数量 3、单价 350.00、运费 50.00、总额 1100.00 CNY。材料中的争议未解决，所以完整证据下的正确动作是 `inspect_dispute`。JSON 中的货币 oracle 使用十进制字符串，方便精确计算；这不改变原生 number 字段的 JSON 数值类型。

### 让可复算的部分独立出来

```python
from decimal import Decimal

quantity = Decimal('3')
unit_price = Decimal('350.00')
shipping = Decimal('50.00')
total = quantity * unit_price + shipping
assert total == Decimal('1100.00')
```

未来接收模型输出时，先检查操作数确实可用、单位一致、数量取值符合任务定义，再计算。不能将 null 当零；不能只因为模型给出的总额合理，就跳过操作数核对。保留模型 `computed_total` 与代码 `total` 两份值，才能区分字段提取错误和计算错误。

一个针对本教学模板的完整规则 baseline 可以先计算金额，再用明确的“争议未解决”／“无未解决争议”句式区分状态；缺少其中任何必需信息时返回补材料。它为模型需要证明的增益提供参照，不宣称已能理解任意争议叙述。

### 三条路径如何公平比较

下游使用同一套有限动作、同一个判断接口及固定任务规则。这里只定义实验 contract，**不把它伪装成 Clairic 的 text 输出，也不改用现有 next-action 的四个动作**。对应的 provider 原生 Choice 请求需要在后续实现时单独构造。

| 路径 | 给下游的输入 | 当前 disputed 案例的合理结果 |
| --- | --- | --- |
| `direct` | 完整原文、规则、判断问题 | `inspect_dispute` |
| `extracted_only` | 规则、问题、数量、单价、运费、币种及代码总额 | `needs_more_context`；投影没有交付状态 |
| `source_linked` | 相同数值，加源 ID/版本与整句验收争议原文 | `inspect_dispute` |

动作还有 `suggest_continue`，用于金额不超限且无未解决争议；`unknown` 则保留给给定动作都不适用的情况。所有分支只产生建议。

这里要分开两种评价。**输入条件下是否诚实**：只见金额时，补材料是正确响应。**是否完成原任务**：它还没有解决这张采购单该做什么。不能为了证明“带来源更好”，把诚实的补材料记成模型错误；也不能只按诚实作答率宣布一个丢掉关键证据的管线同样有用。

### 关键反例：相同金额，对立的验收状态

`amount-clear` 只把最后一句改成：

```text
版本 v2 的验收状态：全部三件已经验收；仓库与供应商记录一致，无未解决争议。
```

完整证据下动作变为 `suggest_continue`，所有数字都保持不变。两份输入经过 `extracted_only` 后完全相同，因此下游无法从这些字段区分它们。这是材料投影造成的信息损失，不应靠下游猜测填补。JSON 同时保存完整证据 oracle 和各路径应有的结果。

先用编辑正确字段运行三种下游输入，隔离“投影有没有保留必要条件”；再在真实提取结果上运行同样比较，评估串联错误。使用编辑字段时明确标注 `editorial_oracle_input`，不能算成提取模型的成绩。

### 指标与失败判据

分别报告操作数正确率、代码总额正确率、模型总额与代码总额差异、状态证据归属正确率、各路径的输入条件下作答正确率，以及原任务得到正确有效建议的比例。另记补材料、unknown、接口失败与整体费用/延迟，不能只保留成功请求。

应揭示的失败包括：操作数错但总额碰巧对；算术全对却忽略未验收状态；错误采用被纠正的供应商旧说法；来源片段只保留“全部已交付”却丢掉“已被仓库纠正”；只见数字时无依据地建议继续。若 `source_linked` 仍截掉决定性限定语，该路径同样失败。

## 实验三：区间是否兑现

### 要回答的问题

模型对一个未知完成时长给出区间后，怎样判断它是否有用？改变输出允许的范围，会不会只是让数字更符合期望？

### 原创输入、请求与事后结果

`estimate-intervals` → `interval-wide-support`：

```text
预测截点：2026-09-01T09:00:00+08:00。目标工单 T-205 在该时刻提交，类型为普通文档校对，共 8 页，预计涉及两个术语核查；提交时队列有 3 件。请预测从提交到完成的日历天数。
在截点前已经完成的同类工单，按完成日期从早到晚，其耗时分别为 2、3、4、4、5、6、7、8 天。这里没有目标工单的完成结果。
```

完整请求使用以下字段；`options.include_quantiles` 为 true：

```json
{
  "completion_days": {
    "type": "estimate",
    "min": 0,
    "max": 30,
    "step": 1,
    "instructions": "预测目标工单 T-205 自提交起至完成的日历天数；这是尚未知晓的结果。"
  }
}
```

时间截点显式写入 `state`。这里不用 `reference_date` 代替时钟：该字段在官方契约中用于为缺少年份的日期提供参照，不能据此假定模型掌握当前时间。[日期契约](../../research/2026-10-20/README.md)

编辑在请求之外安排的原创后续结果是：工单于 2026-09-13 同时刻完成，耗时 12 天。它仅用于教学评分，绝不进入模型输入。这不是实际客户数据，也不是模型测量；尚无 `p10`、`p90` 或任何模型预测概率可报告。

### 确定性 baseline

仅使用截点前的八条历史耗时。点预测取普通样本中位数，为 4.5 天；区间端点使用固定的 nearest-rank 定义 `sorted_values[ceil(p*n)-1]`，得到经验 q10 为 2、q90 为 8，宽度为 6 天。这些数值由给定材料算出，并不称为模型输出，也不承诺覆盖率为 80%。

教学后续结果 12 天落在该 baseline 区间之外。一个案例只能展示怎么算命中，不能用来评判整体校准。要判断是否比这个基线有用，需要更多独立时间组和最终观测。

### 控制变量与时间切分

`interval-narrow-support` 保留同一材料和问题，只将 `max` 从 30 改为 7。编辑结果 12 已经超出这个限制。即使接口返回的数值都合法，现实中的完成时长仍然可以更长。实际响应若带尾部概率字段，原样保留并依据官方定义另行解释；不能因为中心区间落在范围内，就宣布范围外事件不会发生。

未来扩展为历史回测时，用较早时段选任务定义、字段范围和基线方法，冻结后评估较晚的未参与选择的时间组。每次预测只看其截点之前已经可见的信息；一张工单后来的完成日期不能出现在当时的 state 或历史样本中。同源变体保持在同一组，不能将 wide 放开发集、narrow 放测试集。

先收集相同请求的重复结果，再对比范围干预；否则不能把服务本身的波动全部归因于 max 改变。预测与后来观测用稳定工单 ID 关联，观察期结束时还未完成的工单单列 pending/censored，并报告它们占全部预测的比例。

### 指标与失败判据

对已取得最终结果、且预测结构有效的样本计算：

```text
interval_hit = 1 if p10 <= observed_days <= p90 else 0
interval_width = p90 - p10
empirical_coverage = sum(interval_hit) / number_of_evaluable_outcomes
absolute_error = abs(median - observed_days)
```

同时报告全部预测数、可评估结果数、pending/censored 数、接口及结构错误数。以上分母要可见，避免慢工单未完成就从报告中消失。结构有效至少要求数值有限、分位点顺序一致；缺失字段应单独记错，不能给零宽区间。

比较模型与 baseline 时，覆盖率和宽度一起看，并按工单类型、时间段及历史样本多少分组。不能只靠把区间放大获得更高覆盖，也不能把过窄区间的整齐数字当作更精确。小样本报告实际计数，不以单次命中宣布“已经校准”；若后续要设置接受门槛，应在看测试结果之前确定目标覆盖、可接受宽度和样本要求。

应判为实验失效的情况包括：请求中泄漏后续结果；为迎合希望的工期缩窄范围后仍声称没有尾部风险；把 pending 记为零天；只展示区间命中的工单；修改字段或范围后将结果混成同一版本。这些是实验过程错误，先修过程，再讨论模型表现。

## 后续实现需要守住的接口边界

本目录的单值 null、text span、数值操作数和 estimate 区间，都与现有 Choice action/probabilities 不同。若将来实现 collector，应先为本任务定义结果记录和评分，继续保留原始响应、精确输入与来源；不能把任意字段塞进 `choice`，也不能将 null 当作现有 `unknown` action。

实验册、`examples.json` 和方法正文分别负责设计、原创材料与解释。模型实测记录仍应进入独立运行目录，待有实际运行后再补充带条件的观察结论。
