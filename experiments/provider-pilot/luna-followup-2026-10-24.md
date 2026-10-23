# Luna 原生 Decisions 补充实验 · 2026-10-24

## Material Passport

- 状态：本轮采集与离线复算完成；以下设计于首个本轮 POST 前冻结；原生 endpoint 为 OpenRouter `/api/alpha/decisions`，精确模型为 `openai/gpt-6-luna-decisions`。
- 输入：复用[首轮协议](README.md)的原创合成题面、候选与 oracle，不使用私人记忆或实际业务资料。
- 目的：补测上一轮因 ZDR 路由策略未进入正式采集的 Luna；上一轮 missing 和失败不改写。
- 证据：manifest、原始 bytes、attempt 与评分保存在 Git 外本机目录，公开文档只提供设计与汇总。

## 固定设计

四个 primitive probes（4 requests / 6 questions）之后，若 Choice 契约可用，执行首轮固定 subset：30 probability cases 与 33 rule cases，各两次重复。正式 126 requests / 168 questions；总上限 **130 attempts / 174 questions**，每请求最多一次发送，串行，超时 60 秒。未完成和 uncertain 保留，不重新发送。

所有 native bodies 与首轮 Luna 的保留计划一致，只有本次采集顺序与运行身份独立：顺序 seed `20261024` 和 `20261025`。主要指标沿用原协议的世界等权数值 MAE、包含失败的 workflow loss、16 原始函数完整正确率／Hamming loss及改写、候选顺序和 ID 干预；菜单质量、confidence 与数值事件答案保持分离。评价器 `api-capabilities/3`，同一 raw 可离线复算，历史评价不覆盖。

新样本不是原时间块中的同期模型条件。本次与首轮的比较仅为固定题面的异时描述，不能把平台、缓存和时点变化归因于模型；两个重复不能提供总体可靠性或校准保证。已见首轮结果的题本不再冒充新的 held-out test。

## 接入和预算

操作者明确批准本轮原创合成实验临时取消 OpenRouter 的 **OpenAI 分组强制 ZDR**，其余组、禁训练、公开 prompt 和日志设置保持；完成该模型采集后恢复。第一方 OpenAI 标准 abuse monitoring 可能保留内容最多 30 天；本实验不发送私人输入。这是采集策略变化，不是模型能力变化，也不声称请求仍满足 ZDR。依据：[OpenRouter ZDR 的分组及 OR 合并规则](https://openrouter.ai/docs/guides/features/zdr)、[OpenAI 数据控制](https://developers.openai.com/api/docs/guides/your-data)。

本轮独立增量费用上限 **$0.20**，另受已有 key 上限限制；最多 1,000,000 序列化输入 bytes。每次发送前预留所选模型完整 context 的保守费用空间，已知 usage 后核销，未知按完整预留保留，不能以输入估算冒充账单硬上限。无充值、付费 fallback、改模型、Responses 代答或模型建议执行。

## 结果

实际 **130 attempts / 174 questions**，全部 HTTP 200；4 次 primitive 预检的 6 个问题和 126 次正式请求的 168 个问题全部可解析。没有 error、unknown、refusal、missing 或 uncertain，不重试。返回模型 label 为 `openai/gpt-6-luna-decisions-20261006`，provider 为 OpenAI；这是 OpenRouter 原生 Decisions，未调用 ChatGPT 订阅或 Nous。

84 道显式数值题，每世界 28 次：

| 世界 | 数值 MAE / 含失败 workflow loss |
| --- | ---: |
| correlated | 0.0714286 |
| anticorrelated | 0 |
| split | 0.0285714 |
| 三世界等权 | **0.0333333** |

没有调用失败，因此两种数值指标相同。此处从数值 Choice 的答案值计算，不能用原生选项 probabilities 或 confidence 代替。

| 规则条件 | 完整正确 / planned |
| --- | ---: |
| 原始 16 函数 × 2 repeats | **2 / 32** |
| 规则改写 | 2 / 16 |
| 候选倒序 | 2 / 8 |
| opaque ID | 2 / 8 |
| 刻意缺失规则的控制题 | 2 / 2 |

原始函数的含失败 Hamming loss 为 **0.875**。66 个规则回答中，46 次选择业务 `insufficient`；其中仅 2 次属于应当缺失的控制题，其余 44 次发生在有完整规则的函数题。它仍是正常 API Choice，不能改记成 API unknown 或服务失败，也不能因此剔出正确率分母。直接从 raw `answers.*.choice` 对 retained 数值真值及 acceptable 集复算，与统一评价器的 MAE 和 2/32 一致。

预设函数表不变性：改写 16 对中没有一对双方均给出函数表；倒序和 opaque 各 8 对中均有 2 对双方给出表且相同；重复 16 对中 3 对双方给出表且相同。其余 pair 因至少一方选择 insufficient 等而没有可比较的函数表，不等同 HTTP 失败，也不能把剩余配对的相同率解释成整体稳定。

相同旧题本的首轮三世界 MAE 为 Clef 0.0047619、Flash 0.0380952、Jev/Mammoth 0；原始函数正确数分别 8/32、6/32、32/32、32/32。Luna 在这批固定规则上没有达到替代确定性编译的要求；数值和规则能力须分开看。由于异时补测和已见题本，以上是描述性对照，不能推出通用模型排名或生产可靠性。

本补测 provider-reported cost 累计 **$0.006511**，低于 $0.20 增量上限；账户 key 读数另核，不把本机 reservation 称为账单。临时 OpenAI ZDR 例外覆盖本补测及独立角色题本中的 Luna 连续采集，全部 226 次 Luna 请求已经结束；浏览器控制故障使恢复尚待操作者完成／读回，未声称已恢复，其他模型不需要保留该例外。
