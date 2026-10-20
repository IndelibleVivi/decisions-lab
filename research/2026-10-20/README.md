# 2026-10-20 定向更新：Clairic 与类型化取值

[变化索引](updates.json) · [类型化输出方法](../../docs/typed-values.md) · [三组实验题本](../../experiments/typed-values/README.md) · [10-15 契约调查](../2026-10-15/README.md)

本轮核查 Cloudflare 在 **2026-10-19** 发布的 Clairic preview、类型化取值契约和 Workers AI 标价。材料来自八项官方来源；其中模型 schema 和示例固定到文档仓库 revision。研究性质是文档与 schema 检查，**尚未调用模型**。首期 census 和 10-15 调查保留各自日期，本轮不刷新 Jev、OpenAI Decisions 或其他供应商的版本和价格。

## 这次真正增加了什么

Clairic 扩展了 Lab 要研究的输出空间：过去的实验给出有限动作供模型选择，现在还需要研究从材料中取得文本、数值、日期，以及估计未知数值的行为。它在 Workers AI 的标识为 `@cf/cloudflare/clairic`。发布时是 hosted preview，开放权重仍是计划。[发布说明](https://developers.cloudflare.com/changelog/post/2026-10-19-clairic-workers-ai/)

“结构化输出”本身已经存在：Workers AI 的 LLM JSON Mode 使用 `response_format` 描述 JSON 格式。Clairic 则有独立的字段请求和数值解码语义。两者不能因最后都能表示为 JSON 而共用未经核对的 adapter。[JSON Mode](https://developers.cloudflare.com/workers-ai/features/json-mode/)

| 想问的问题 | 输出对象 | 在 Lab 中怎样处理 |
| --- | --- | --- |
| 下一步核对来源、比较契约，还是补材料？ | 已知选项及其分布 | 继续使用已有 Choice 实验 |
| 这份材料写的是哪个编号、日期、价格？ | 有类型的字段值及来源线索 | 新的取值实验；逐字段检查 |
| 材料给出的数量和单价合计多少？ | 可以计算的值 | 与确定性计算对照 |
| 一个尚未发生的结果可能是多少？ | 预测值与区间 | 冻结预测时点，等观测结果评分 |
| 为什么发生、如何解释或写成一段话？ | 开放内容 | 保留生成式模型这一工具类别 |

这是本项目的任务划分，不是统一的模型质量排行榜。Cloudflare 的概念页也区分提取、计算、估计与预测；它明确指出类型约束不能保证事实正确。[Extraction models](https://developers.cloudflare.com/workers-ai/concepts/extraction-models/)

## 原生请求：state 与 fields

Worker binding 使用 `env.AI.run("@cf/cloudflare/clairic", body)`；REST 使用下列路径和 Bearer 认证。这里仅展示请求，不发起网络调用。

```text
POST https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/cloudflare/clairic
Authorization: Bearer <token>
Content-Type: application/json
```

下面是本项目原创输入，按照已核 schema 编写；没有相应模型结果。

```json
{
  "model": "clairic",
  "state": "通知：测试批次 R-17 的截止日期为 2026-11-04。",
  "fields": {
    "batch_id": {"type": "text", "instructions": "测试批次编号"},
    "deadline": {"type": "date", "instructions": "截止日期"}
  },
  "options": {"return_state_text": true}
}
```

模型 reference 将 `model` 和至少一个 `fields` 字段列为 required，因此示例保留 `model`，不从博客中省略它的片段推导兼容行为。`reference_date` 的文档含义是为没有年份的日期提供锚点；需要“今天”的计算应在输入中明确当前日期。[模型页](https://developers.cloudflare.com/workers-ai/models/clairic/) · [固定 schema](https://github.com/cloudflare/cloudflare-docs/blob/39cb53c8e8aa663096c589831bcecd1e5d657641/src/content/workers-ai-models/clairic.json)

| 字段族 | 已核的声明 | 实验时最需要区分的东西 |
| --- | --- | --- |
| `text` | 原文片段和位置 | 片段存在，不代表选对了实体 |
| `number`、`duration` | 数值、单位和精度设置 | 提取与计算；标签单位与实际换算 |
| `date`、`time`、`datetime` | 对应的日期时间值 | 写明的日期、推算结果与时间语境 |
| `list` | `items` 为 text、number 或 date | 空数组、漏项与重复项 |
| `estimate` | 声明范围和网格，返回分布摘要 | 预测和已知事实；区间覆盖与宽度 |
| `forecast` | 按步预测，`horizon` 为 1–64 | 每一步的误差及时间泄漏 |

字段配置不是任意嵌套 JSON Schema。原始输出的 `value` schema 本身很宽，客户端仍需要按请求字段类型校验返回。当前模型页的 “Text Generation” 分类标签也不能替代这些实际字段定义。

Binding 示例直接读取 `response.answers`，REST 结果有 Workers AI 的 `result` 外层。模型 schema 的 answer 只强制 `type` 和 `value`；`confidence`、span 等辅助字段并非全部必填。以后实现 collector 时，应分别处理 transport envelope、字段类型和可选元数据，不能把缺少辅助信息直接当成缺失答案。[官方示例源码](https://github.com/cloudflare/cloudflare-docs/blob/39cb53c8e8aa663096c589831bcecd1e5d657641/src/components/models/code/ClairicCode.astro)

## 一个很容易接错的返回

官方示例中的采购单号不存在，返回却同时包含这些信息：

```text
value = null
guess = INV-2291
p_null = 1
confidence = 0.9995
```

这个例子来自[模型页](https://developers.cloudflare.com/workers-ai/models/clairic/)，不是本项目实测。**不能用高 confidence 把 guess 填回 value。** 如果调用方只看置信度，它会把发票号移作不存在的采购单号。实验要分别检查“有没有答案”“候选是什么”“采用了什么”，并把这种接线错误与模型选错实体分开。

原始 schema 暴露 `null_threshold`，默认 0.5，并描述为 `p_null` 超过阈值时返回 null；调整它会改变缺失值策略，应保存为实验条件。当前读取的 schema 没有给出 confidence 的计算公式，也没有明确 span 的编码单位和端点约定。中文、emoji 与组合字符的定位需要实际探针，不能先假定 JavaScript 切片下标与服务端完全相同。

## 价格、用量和两个待测边界

以下是 **2026-10-20** 读取的公开标价，单位为 **美元／百万输入 tokens**；它们不是本项目账单。[Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/)

| 路线 | 输入价格 |
| --- | ---: |
| Clef | $0.240 |
| Clef-flash | $0.038 |
| Clef-omni | $0.150 |
| Clairic | $0.100 |

Clairic 不生成输出 tokens。计费分析应保存 provider 的 `usage.input_tokens` 和 `passes`：官方示例中 `state_tokens=61`、`schema_tokens=472`、`passes=3`，而 `input_tokens=655`。它恰好满足 `61×3+472`，但一个示例不足以确立所有输入形态的计费公式。用完整 `input_tokens` 乘标价是估算，仍不等于实际账单。

有两项值得保留为 **待测问题**：

- 模型属性列出 65,536 context，字段说明却写按 8,192-token pass 分组。当前来源没有解释二者关系；不能据此声称 64K 原文完整进入每一轮，也不能断言总窗口只有 8K。长输入实验应保留 `truncated`，并在请求中启用 `options.return_state_text` 检查实际定位文本。
- schema 将字段数量描述为无单独上限，并会分成多个 passes。字段数增长是否增加延迟、输入重复计量或引起截断，需要分别观察。

这些是文档之间的待核边界，不是已复现的服务端故障。图片输入的具体大小与格式另见模型 reference；本轮题本先使用文本，不把图像能力自动写成已验证覆盖。

## 对内容与后续实验的判断

本轮新增[方法章](../../docs/typed-values.md)和[三组实验题本](../../experiments/typed-values/README.md)，让读者能够沿具体输入判断错误在哪一环。它们分别考察缺失字段、取值后计算与上下文损失、预测区间的检验。原创请求、编辑答案和干预方案可以作为后续采集的起点；模型结果仍为空。

Clairic 不应直接挂到现有 Choice collector：已有 `decision_lab` 契约围绕固定 next-action、可接受动作集合和概率回放建立。新的 scalar null、list 和 estimate 需要独立的输出契约。现在先把问题、输入和评分写清楚，后续才能判断值得实现哪一条采集路径。

我们也不预设“提取 → 决策模型 → 生成模型”总是更优。已提取数值如果足以用明确规则判断，就让代码完成；需要语义解释才引入新的模型步骤。每增加一次转换，都应同时测它减少了哪些噪声、丢掉了哪些限定条件。

Cloudflare 的发布文章把多步算术和预测列为早期能力，并建议将计算交给代码。这里采用的是可检验的分工，不引用厂商示例的提速和准确率作为本项目收益。[发布文章](https://blog.cloudflare.com/clairic-extraction-model/)

## 来源与复查范围

| ID | 来源 | 本轮读到什么 |
| --- | --- | --- |
| CF-CLAIRIC-RELEASE | [10-19 changelog](https://developers.cloudflare.com/changelog/post/2026-10-19-clairic-workers-ai/) | 发布日期、preview、开放权重计划与类型介绍 |
| CF-CLAIRIC-BLOG | [发布文章](https://blog.cloudflare.com/clairic-extraction-model/) | 设计定位、示例和作者自述局限 |
| CF-CLAIRIC-MODEL | [模型页](https://developers.cloudflare.com/workers-ai/models/clairic/) | 请求、官方响应示例、用量与窗口声明 |
| CF-CLAIRIC-SCHEMA | [固定 revision 的 JSON](https://github.com/cloudflare/cloudflare-docs/blob/39cb53c8e8aa663096c589831bcecd1e5d657641/src/content/workers-ai-models/clairic.json) | 原生字段、options、输入输出 schema |
| CF-CLAIRIC-EXAMPLE | [固定 revision 的示例源码](https://github.com/cloudflare/cloudflare-docs/blob/39cb53c8e8aa663096c589831bcecd1e5d657641/src/components/models/code/ClairicCode.astro) | Binding／REST 包装差异；作者标注为真实响应、概率经舍入 |
| CF-EXTRACTION | [概念说明](https://developers.cloudflare.com/workers-ai/concepts/extraction-models/) | 取值、计算、估计、预测的任务区别 |
| CF-PRICE | [价格页](https://developers.cloudflare.com/workers-ai/platform/pricing/) | 本页四条路线的输入标价 |
| CF-JSON-MODE | [JSON Mode](https://developers.cloudflare.com/workers-ai/features/json-mode/) | 生成式结构化输出的另一条请求路径 |

直接打开公告和博客遇到访问错误后，本轮通过搜索服务取回官方正文；访问方法记在 [updates.json](updates.json)。模型 schema 通过官方 GitHub 仓库读取。所有本轮结论止于这些资料，模型效果与账号可用性等待真实采集。
