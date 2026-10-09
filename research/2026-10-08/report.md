# Decision Models & APIs · 2026-10-08

> 研究截点：2026-10-08 UTC。2026-10-09 整理为可维护的公开版。报价与产品状态属于该日期快照；本轮没有新的模型推理。

## 01 · 研究结论

Decision API 已经形成一个有多种实现路线的市场。现阶段，最有用的比较单位是 **模型与版本 × 实际服务渠道 × 任务契约**。供应商名称、统一接口名称或首页 token 单价，都不足以独立决定选型。

**F01 · 契约兼容需要逐字段核验。** 相同的 `confidence`、`score` 和多问题请求，在不同服务中有不同含义。模型分布、SDK 转换、网关包装和业务阈值应各自留下记录。[[3]](https://docs.typesafe.ai/confidence "Jev confidence 定义")[[20]](https://docs.fastino.ai/inference/systemone "Fastino GLiDE System One 契约")[[19]](https://developers.telnyx.com/docs/inference/decision-models "Telnyx Decision Models Beta 契约")

**F02 · 完整工作流决定价格优势。** 输入如何重复计费、是否发生思考、升级率、重试、检索和媒体开销，都可能改变排序。对短标签任务，便宜生成模型也是必要对照。[[22]](https://levanto.ai/pricing "Levanto Sage 计费与套餐")[[16]](https://developers.openai.com/api/docs/models/gpt-6-luna "GPT-6 Luna 模型级报价与上下文")[[46]](https://www.pixelsandpatterns.org/p/jev-is-fast-is-it-better-than-llms "原作者方法与新 Decisions endpoint 澄清")

**F03 · 原生分布很有价值，校准仍然属于具体任务。** 公开预测复算显示，Jev 在所查工具选择子集为 398/400，在特定历史模型路由子集为 200/400。任务定义、输入信息和标签来源必须一起阅读。[[41]](https://github.com/David-DL-Space/sys1-eval "sys1-eval 原始预测、构造与分析仓库")

**F04 · 开放模型的工程路线已经可用来做认真对照。** Clef、Liquid d1 开放版本、Laya、Tev、Kev 等覆盖不同结构和运行时。当前 llama.cpp 已有原生 System One 支持；许可、模型文件、正确推理路径和硬件费用仍需逐项登记。[[37]](https://github.com/ggml-org/llama.cpp/releases/tag/v0.6.0 "llama.cpp v0.6.0 正式发行")[[38]](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md "llama.cpp 当前 server API 文档")[[25]](https://docs.liquid.ai/lfm/models/d1-3b.md "Liquid d1-3B 文档")[[59]](https://github.com/NandhaKishorM/laya "Laya 原作者仓库")[[60]](https://huggingface.co/togethercomputer/Tev1-4B-experimental "Together Tev1-4B-experimental 模型卡")

本轮完成了公开文档核验、部分实现路径审读、六项实践或研究的证据审读，以及 1,000 个公开案例、4,000 份历史预测记录的离线复算。没有进行新的模型推理调用；实时延迟、实际扣费、当前中文准确率和账户可用性保留为未实测项。公开结论与具体个人项目的采用备忘录分开，后者可以引用 F01–F08 等稳定编号。

## 02 · 范围、证据与市场边界

这里的 Decision Models / Decisions APIs 指：应用提供上下文和有边界的判断问题，服务返回类别、是非分数、有序等级、候选分布或受限工具选择。包括专门决策头、可输出候选概率的语言模型、兼容服务和专用行为判断器。本文没有把所有规则引擎、授权策略产品、传统风控 API 或通用 LLM 产品都计作专门供应商。

| 层级 | 登记内容 | 去重原则 |
| --- | --- | --- |
| 原厂模型 / 服务 | 模型家族、版本、原生接口、公开身份 | 名称相似与接口相同都不能证明底层模型相同 |
| 托管与网关路线 | OpenRouter 实际 upstream、Vercel、Workers AI、国内接入等 | 每条路线单独记录价格、模态、上下文和限制；别名不算新训练方 |
| 本地模型与运行时 | 权重、量化、代码许可、正确决策头路径 | SDK、adapter、runtime 与 checkpoint 分开 |
| 对照与相邻能力 | 生成模型的结构输出 / logprobs、reranker、专门分类器、规则与检索 | 按同一任务质量、响应时间和完整成本比较 |

证据按 **官方契约或目录、原作者代码、作者实测、独立离线复算、尚未确认** 区分。官方 benchmark 是作者实测；文档中的示例响应只是示例。来源之间不一致时保留双方，写明版本、路线和核验日期。研究覆盖英文与中文的一手文档、主要网关目录、论文和原作者仓库；这是一个可增量维护的市场快照，无法证明未被发现的产品不存在。

下面的供应商表用于快速定位；附录保留更细的 model × route 记录、限制与证据。`unknown` 表示本轮未确认；目录中 `context_length: 0` 不解释为无限上下文。免费预览、免费档与正式单价分别标注。

23 项原厂模型与服务条目 · 按归属收束，不等同于 23 家独立训练机构

| 原厂 / 模型 | 交付形态 | 能力 | 公开报价 | 契约与限制 |
| --- | --- | --- | --- | --- |
| **TypeSafe · Jev 1.13**[[1]](https://docs.typesafe.ai/models "TypeSafe Jev 官方模型、上下文与报价")[[2]](https://docs.typesafe.ai/api "TypeSafe System One API 契约") | 托管 | 文本 / JSON；三原语；问题隔离 | $0.042/M 输入 | 64K 总量 / 32K 单问；保存返回版本 |
| **Cloudflare · Clef / Clef-flash**[[6]](https://developers.cloudflare.com/workers-ai/models/clef/ "Cloudflare Clef hosted schema")[[7]](https://developers.cloudflare.com/workers-ai/models/clef-flash/ "Cloudflare Clef-flash hosted schema")[[9]](https://huggingface.co/Cloudflare/clef-flash "Cloudflare Clef-flash 模型卡")[[11]](https://openrouter.ai/cloudflare/clef "OpenRouter Clef routes") | 托管与开放 | 文本 / 图片；joint schema；HF / GGUF | 原生 $0.24 / $0.09；OR 另价 | hosted 有效文本窗口存在文档差异；本地视频另列 |
| **OpenAI · GPT-6 Luna Decisions**[[14]](https://developers.openai.com/api/docs/guides/decisions "OpenAI Decisions guide")[[15]](https://developers.openai.com/api/reference/resources/decisions/methods/create "OpenAI Decisions endpoint reference")[[16]](https://developers.openai.com/api/docs/models/gpt-6-luna "GPT-6 Luna 模型级报价与上下文")[[18]](https://developers.openai.com/api/docs/changelog "OpenAI changelog：2026-10-06 Decisions public beta") | 托管 | predicate / choice / score；文字与 inline 图片；逐问 refusal | $0.10/M 输入；地区 / 长输入附加条件 | 10 月 6 日 public beta；模型级 1.05M 与 endpoint 分开 |
| **Perplexity · Decider v1.1 27B**[[103]](https://docs.perplexity.ai/docs/decisions/quickstart "pplx_api")[[36]](https://openrouter.ai/perplexity/pplx-decider-v1.1-27b "OpenRouter Perplexity Decider V1.1 27B") | 托管 | 文本 / JSON / 图片；128 问；262,144 context | $0.02/M 输入，输出免费 | 原生 /v1/decisions 与 OR；v1.1 权重许可未核清 |
| **Liquid AI · d1 / d1-3B / d1-omni**[[23]](https://docs.liquid.ai/lfm/models/d1.md "Liquid hosted d1")[[87]](https://huggingface.co/LiquidAI/d1-3B "liquid_open_3b")[[88]](https://huggingface.co/LiquidAI/d1-omni-600M "liquid_open_omni")[[24]](https://vercel.com/ai-gateway/models/d1 "Vercel Liquid d1 route") | 托管与开放 | 原生图文；开放 3B 图文、omni 短音频 / 图文 | OR / Vercel $0.04/M；原生数值未确认 | 图片随问题重复计费；开放模型 lfm1.0；模态 / context 分路线 |
| **Upstage · Solar Decide / Flash**[[34]](https://console.upstage.ai/docs/models/solar-decide "Upstage Solar Decide 原厂文档")[[104]](https://console.upstage.ai/api/systemone "solar_api")[[91]](https://openrouter.ai/api/v1/models?output_modalities=decisions "openrouter_models") | 托管 | 文本；三原语；524,288 context | 原生 Decide $0.10/M；OR $0.05/M | Beta；OR Decide 促销；Flash 当日入目录，原生契约未确认 |
| **Fastino · GLiDE**[[20]](https://docs.fastino.ai/inference/systemone "Fastino GLiDE System One 契约")[[21]](https://docs.fastino.ai/pricing "Fastino 定价")[[98]](https://docs.fastino.ai/concepts/glide "fastino_glide") | 托管 | 三原语；每问 40K；不确定时可增加 reasoning | $0.15/M 输入；输出 $0 | score=众数下标，expected\_level=期望；输入累计内部 passes |
| **Fastino · GLiNER2.5-Decide**[[99]](https://huggingface.co/fastino/GLiNER2.5-Decide "gliner_card")[[21]](https://docs.fastino.ai/pricing "Fastino 定价") | 托管与开放 | schema 分类；单标签 / 多标签；多种大小和语言 | 已核 hosted GLiNER-2.5-Decide $0.03/M 输入；输出 $0 | 各开放 checkpoint 本地另算；GLiDE System One 契约独立 |
| **Alibaba Cloud · decision-model-preview**[[30]](https://www.alibabacloud.com/help/en/model-studio/decision-model-preview "Alibaba Cloud decision-model-preview")[[86]](https://www.alibabacloud.com/help/en/model-studio/decision-model-api "alibaba_api") | 托管 | 文本 / JSON；三原语；65,536 context | 北京 / 新加坡限时免费 | Preview；1200 RPM / 2M TPM；Score 范围与溢出行为有歧义 |
| **Telnyx · Decision Flash / Pro**[[112]](https://telnyx.com/products/decision-models "telnyx_product")[[19]](https://developers.telnyx.com/docs/inference/decision-models "Telnyx Decision Models Beta 契约") | 托管 | 文本 / JSON；最多 64 问；2–64 候选 / 等级 | Flash $0.035/M；Pro $0.20/M | Beta；底层模型由服务管理；confidence 为归一化熵 |
| **Respan · span-01 / Lite**[[107]](https://www.respan.ai/docs/apis/gateway/run-span-01 "respan_scores")[[29]](https://www.respan.ai/docs/documentation/span-01/concept "Respan span-01 契约与报价")[[108]](https://www.respan.ai/docs/documentation/span-01/quickstart "respan_quickstart") | 托管 | trace 行为判断；present / absent / not observable | Pro $0.02/M；Lite 有上限免费 | 早期接入按组织；原生三路与网关 Noul 投影分开 |
| **EmpirioLabs · Aplomb 1**[[28]](https://docs.empiriolabs.ai/decisions "EmpirioLabs Decisions 完整接口与条件分布")[[27]](https://docs.empiriolabs.ai/models/aplomb-1 "EmpirioLabs Aplomb 1 官方模型契约") | 托管 | 图文 / 音视频；三原语、受限 tool；abstain | $0.02/M 输入；输出免费 | 公开 1M、fast / full；state 每请求一次；本轮无当前质量实测 |
| **Levanto · Sage**[[22]](https://levanto.ai/pricing "Levanto Sage 计费与套餐")[[110]](https://platform.levanto.ai/api/intelligence/skill "levanto_contract") | 托管 | Yes/No、Choice、Scale、Sort、Tags；图片；可选思考 / 搜索 | 输入 $0.038–0.05/M；思考 $10/M；搜索 $0.10/次 | 费率对应套餐；按 question / tag / sort item 重复内容 |
| **Databricks · ai\_decide**[[32]](https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_decide "Databricks ai_decide SQL 契约")[[111]](https://docs.databricks.com/api/ai-functions/v1/ai-decide "databricks_rest")[[33]](https://www.databricks.com/blog/introducing-aidecide-make-fast-decisions-your-governed-data "Databricks ai_decide 发布说明") | 托管 | SQL + REST；文本 / structured data；三原语 | 专属数值价格未确认 | Beta / 区域 / Runtime 条件；后台 checkpoint 未公开 |
| **Inception · Mercury Decide**[[105]](https://openrouter.ai/inception/mercury-decide:free "mercury_route")[[106]](https://www.linkedin.com/posts/inception-labs-ai_introducing-mercury-decide-the-most-intelligent-activity-7511141315691057154-Kq_H "mercury_announcement") | 托管 | 三原语；文字；32,768 context | OR 免费 early-access route | 免费路线有限速；不据生成模型名称推断决策架构 |
| **Together · Tev1-4B-experimental**[[94]](https://github.com/togethercomputer/tev1 "tev_repo")[[60]](https://huggingface.co/togethercomputer/Tev1-4B-experimental "Together Tev1-4B-experimental 模型卡")[[91]](https://openrouter.ai/api/v1/models?output_modalities=decisions "openrouter_models") | 托管与开放 | Qwen3.5-4B 微调；next-token 字母分类；原生示例 2–24 选项 | OR $0.042/M；直连价格未确认 | Experimental；代码 MIT，权重许可待定；32K 为 OR 目录口径 |
| **Jared Palmer · Kev**[[95]](https://github.com/jaredpalmer/kev "kev_repo")[[91]](https://openrouter.ai/api/v1/models?output_modalities=decisions "openrouter_models") | 托管与开放 | Qwen + LoRA / pointer head；0.8B / 4B / 9B / 27B | 4B OR $0.042/M；其余本地成本 | Kev 1.0；小模型已验证 8K、27B 64K；温度随 checkpoint |
| **Convai Innovations · Laya**[[59]](https://github.com/NandhaKishorM/laya "Laya 原作者仓库")[[92]](https://huggingface.co/convaiinnovations/laya "laya_model")[[93]](https://github.com/NandhaKishorM/laya/blob/3cf26cbcb18725dbc2d127bb8bb2c4c43243ae63/laya/confidence.py "laya_confidence") | 开放模型 | encoder typed heads；English / multilingual / typed | 自托管资源成本；无已核商业单价 | 默认窗口 512 / 1024；多语温度未拟合；更长窗口显式配置 |
| **OzLabs · Typical**[[96]](https://github.com/ozlabsai/typical "typical_repo")[[97]](https://github.com/ozlabsai/typical/blob/main/releases/typical-small.md "typical_release") | 开放模型 | contextual candidate heads；新 Noul Bernoulli；factored null | 自托管资源成本 | preview / 当前版本结构不同；保留训练数据许可问题 |
| **Bespoke Labs · Nimble**[[100]](https://huggingface.co/bespokelabs/Bespoke-Nimble-9B "nimble_card")[[101]](https://github.com/bespokelabsai/nimble "nimble_repo")[[102]](https://github.com/bespokelabsai/nimble/blob/main/docs/TRY_NIMBLE.md "nimble_demo") | 开放模型与演示 | 9B；候选 token scoring；MLX prefix 并行 | 本地资源成本；demo 无已核商业报价 | 当前 local 8K / 255 / T=1 与 demo 26 / fitted T 分开 |
| **xuhaodev · Qwen3.5-4B-Jev**[[114]](https://huggingface.co/xuhaodev/Qwen3.5-4B-Jev "xuhao_card") | 开放模型 | 中文研究路线；LoRA + FP32 scalar head；三原语 | 自托管资源成本 | Apache-2.0；4K 单候选执行上限与质量验证分开 |
| **CountingSheep / Xiaooolong · Vev**[[115]](https://huggingface.co/CountingSheep/vev-4b "vev_card") | 开放模型 | Qwen 后训练；4B / 9B；中英图文 | 自托管资源成本 | CC BY-NC 4.0；底模许可不替代微调的非商用限制 |
| **WhaletechAI · W1-JEV**[[116]](https://huggingface.co/WhaletechAI/W1-JEV "w1_card") | 开放模型 | 语言扩散模型后训练；约 3.74B；结构化判断 | 自托管资源成本 | 研究发布；默认 runtime 4K；精确契约和许可未核清 |

5 条主要服务渠道与接入边界

| 服务渠道 | 接口 / 标识 | 需要单独记录的条件 |
| --- | --- | --- |
| OpenRouter | `/api/alpha/decisions` `/api/v1/systemone` | 保存实际 upstream、返回版本、usage.cost；同模型不同承载方的价格和有效上下文可能不同。[[11]](https://openrouter.ai/cloudflare/clef "OpenRouter Clef routes")[[12]](https://openrouter.ai/cloudflare/clef-flash "OpenRouter Clef-flash routes")[[79]](https://openrouter.ai/docs/guides/community/jev "OpenRouter Decisions route and aliases")[[80]](https://openrouter.ai/docs/guides/community/typesafe-sdk "Native TypeSafe SDK can target OpenRouter systemone route") |
| Vercel AI Gateway | `typesafe-ai/jev` 等网关标识 | Jev 当前列 TypeSafe AI / DigitalOcean；显示价格精度、SDK 的 boolean 等字段与原生协议分别核验。[[57]](https://vercel.com/ai-gateway/models/jev "Vercel Jev route 与显示报价")[[24]](https://vercel.com/ai-gateway/models/d1 "Vercel Liquid d1 route") |
| Cloudflare | Workers AI 原生 第三方 AI route | Clef 使用带 @cf 路径的原生服务；Jev 使用第三方模型标识 typesafe/jev 与另一请求 envelope。共享免费额度不按模型重复分配。[[6]](https://developers.cloudflare.com/workers-ai/models/clef/ "Cloudflare Clef hosted schema")[[82]](https://developers.cloudflare.com/ai/models/typesafe/jev/ "Cloudflare third-party Jev route; envelope, price and ZDR catalog label")[[8]](https://developers.cloudflare.com/workers-ai/platform/pricing/ "Cloudflare Workers AI 定价") |
| 腾讯 EdgeOne Makers | `@makers/jev` `https://ai-gateway.edgeone.link/v1/systemone` | Jev 转售入口；使用 EdgeOne key，无需另备 TypeSafe key。共享 Makers 月度免费 Token 额度，精确额度 / 付费率本轮未核。[[113]](https://cloud.tencent.com/document/product/1552/138731 "tencent_route") |
| 本地 System One | llama.cpp + 模型 GGUF / projector | 这是运行时路线；模型身份和许可另记。Clef 联合决策、ubatch 与 projector 约束成立，不能自动继承其他服务的 confidence。[[37]](https://github.com/ggml-org/llama.cpp/releases/tag/v0.6.0 "llama.cpp v0.6.0 正式发行")[[38]](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md "llama.cpp 当前 server API 文档") |

## 03 · 能力比较：六个会改变集成结果的细节

### F05 · 同名 confidence 可能是三种统计量

给定完全相同的四选一分布 `[0.7, 0.1, 0.1, 0.1]`，按已核验的定义计算：

| 具体实现 / 文档 | 定义 | 此例结果 | 证据范围 |
| --- | --- | --- | --- |
| Jev Choice | (最高概率 − 1/N) / (1 − 1/N) | 0.6000 | 当前原厂文档 |
| Clef-flash HF helper | 最高概率，四位舍入 | 0.7000 | 固定 revision 的本地代码路径 |
| Telnyx Choice / Score | 1 − H(p) / ln(N) | 约 0.3216 | 当前 Beta 文档，归一化熵 |

这些是纯公式演示。统一使用 `confidence ≥ 0.65` 会得到不同分支。它们都不能在未验证的任务中直接解释为“真实正确率”。Telnyx 明确将其分布描述为候选间相对偏好。[[3]](https://docs.typesafe.ai/confidence "Jev confidence 定义")[[10]](https://huggingface.co/Cloudflare/clef-flash/blob/41318bf2106d135c7a92da745fec4b255279b4de/joint_schema_model.py "Clef-flash 固定 revision Python helper")[[19]](https://developers.telnyx.com/docs/inference/decision-models "Telnyx Decision Models Beta 契约")

Clef 托管 confidence 的计算方式尚未确认：OpenRouter 官方图片示例的最高概率为 0.9844，confidence 为 0.9536，与上述本地 helper 不一致，也不符合 Jev 的对应公式。该差异可能涉及服务实现或样例本身；本轮没有据此反推托管公式。[[13]](https://openrouter.ai/docs/guides/community/multimodal-decisions "OpenRouter 多模态 Decisions 契约与样例")

### 评分：期望、众数与实际数量分别处理

Jev 与多数兼容接口的 Score 表示有序等级下标的期望。Fastino GLiDE 的 `score` 是最可能等级的整数下标，期望另放在 `expected_level`。迁移时直接读同名字段会改变业务逻辑。[[2]](https://docs.typesafe.ai/api "TypeSafe System One API 契约")[[20]](https://docs.fastino.ai/inference/systemone "Fastino GLiDE System One 契约")

纯数学例子：等级 0、1、2 上的分布 `[0,1,0]` 与 `[0.5,0,0.5]` 都有期望 1；前者集中在中间，后者在两端分裂。保存完整分布能够保留这一区别。等级描述构成序数量表；用其期望还原精确金额、计数或日期需要另一个明确模型，精确算术应交给代码。

### 共享上下文与问题独立性

Jev 文档将多问题定义为对同一 state 并行且隔离地求值，question key 不作为模型指令。Clef 的 joint schema head 具有跨字段交互；已读本地 helper 把 question ID 编入输入，缺少 instructions 时还用 ID 后备。追加问题、改变 key 与改变顺序应成为独立控制变量。联合求值本身并未提供任意业务逻辑约束保证。[[4]](https://docs.typesafe.ai/introduction "Jev 多问题隔离语义")[[2]](https://docs.typesafe.ai/api "TypeSafe System One API 契约")[[9]](https://huggingface.co/Cloudflare/clef-flash "Cloudflare Clef-flash 模型卡")[[10]](https://huggingface.co/Cloudflare/clef-flash/blob/41318bf2106d135c7a92da745fec4b255279b4de/joint_schema_model.py "Clef-flash 固定 revision Python helper")

### F06 · 上下文需要记录实际可读证据范围

| 路径 | 已核验的口径 | 采用时如何处理 |
| --- | --- | --- |
| Jev 原生 | state + 全部 questions 合计 64K；state + 最长 question 为 32K | 分别校验两个预算 |
| Clef hosted / OpenRouter | 原生标示 65,536；OR 对 Workers AI 路线提示 state 约取前 2K | 保留文档冲突，做首尾证据探针 |
| Clef 固定 HF helper | max\_length 默认 16,384，并按 schema / 媒体占用截短 state | 只适用于这条本地调用路径 |
| OpenAI Decisions | Luna 模型页为 1,050,000；endpoint 单独的有效边界未确立 | 模型级 context 与 endpoint 验证分开 |
| Aplomb 1 | state + 最长问题上限 1M；state 超过 131,072 默认 fast，可选 full；评估问题数 >8 强制 full | tool 及其 enum / boolean 参数计入评估问题数；验证尾部证据 |

依据：[[1]](https://docs.typesafe.ai/models "TypeSafe Jev 官方模型、上下文与报价")[[6]](https://developers.cloudflare.com/workers-ai/models/clef/ "Cloudflare Clef hosted schema")[[11]](https://openrouter.ai/cloudflare/clef "OpenRouter Clef routes")[[10]](https://huggingface.co/Cloudflare/clef-flash/blob/41318bf2106d135c7a92da745fec4b255279b4de/joint_schema_model.py "Clef-flash 固定 revision Python helper")[[16]](https://developers.openai.com/api/docs/models/gpt-6-luna "GPT-6 Luna 模型级报价与上下文")[[27]](https://docs.empiriolabs.ai/models/aplomb-1 "EmpirioLabs Aplomb 1 官方模型契约")[[28]](https://docs.empiriolabs.ai/decisions "EmpirioLabs Decisions 完整接口与条件分布")

### 模态属于实际接口

Cloudflare 托管 Clef 当前接受最多 4 张图片，原作者本地材料还涵盖视频帧；托管视频接口未确认。OpenAI Decisions 参考文档接受最多 128 张 inline data URL 图片，并不接受普通远程 URL、音频、文件和工具调用。Liquid 原生 d1 与网关 d1 的当前模态登记也不同。模型卡上的能力需要映射到真正使用的 endpoint。[[7]](https://developers.cloudflare.com/workers-ai/models/clef-flash/ "Cloudflare Clef-flash hosted schema")[[9]](https://huggingface.co/Cloudflare/clef-flash "Cloudflare Clef-flash 模型卡")[[15]](https://developers.openai.com/api/reference/resources/decisions/methods/create "OpenAI Decisions endpoint reference")[[23]](https://docs.liquid.ai/lfm/models/d1.md "Liquid hosted d1")[[24]](https://vercel.com/ai-gateway/models/d1 "Vercel Liquid d1 route")

### 缺少证据、拒绝与失败需要保留

Respan 原生每个行为有 present、absent、not observable 三类概率；其网关 Noul 映射不应被当作完整三类分布。Aplomb 的 abstain 单独给出信息不足概率，其余答案分布以“输入包含回答所需信息”为条件；OpenAI 有逐问题 refusal。业务层最好分别处理“输入无法回答”“模型拒绝”“请求失败”和正常答案，以免缺少证据被误记成否定。[[29]](https://www.respan.ai/docs/documentation/span-01/concept "Respan span-01 契约与报价")[[28]](https://docs.empiriolabs.ai/decisions "EmpirioLabs Decisions 完整接口与条件分布")[[15]](https://developers.openai.com/api/reference/resources/decisions/methods/create "OpenAI Decisions endpoint reference")

## 04 · 价格：从标价到完整成本

全部报价为 2026-10-08 所查公开页面，币种 USD。路线促销、套餐与免费额度不构成长期承诺。下表算例统一设定 **100 万次请求，每次 1,000 个可计费输入 token**；这不表示相同原始文本在各接口会被计为同样 token，更不表示质量或延迟相同。

13 个可比计费算例 · 每次 1,000 个可计费输入 token；不含质量、延迟或账单实测

| 具体模型与路线 | 每百万输入 token | 100 万次请求的输入算例 |
| --- | --- | --- |
| Jev / TypeSafe native[[1]](https://docs.typesafe.ai/models "TypeSafe Jev 官方模型、上下文与报价") | $0.042 | **$42** |
| Clef-flash / Cloudflare native[[7]](https://developers.cloudflare.com/workers-ai/models/clef-flash/ "Cloudflare Clef-flash hosted schema") | $0.09 | **$90** |
| Clef / Cloudflare native[[6]](https://developers.cloudflare.com/workers-ai/models/clef/ "Cloudflare Clef hosted schema") | $0.24 | **$240** |
| GPT-6 Luna Decisions / OpenAI native[[16]](https://developers.openai.com/api/docs/models/gpt-6-luna "GPT-6 Luna 模型级报价与上下文") | $0.1 | **$100** |
| Liquid d1 / Vercel route[[24]](https://vercel.com/ai-gateway/models/d1 "Vercel Liquid d1 route") | $0.04 | **$40** |
| Clef-flash / OpenRouter Prime Intellect route[[12]](https://openrouter.ai/cloudflare/clef-flash "OpenRouter Clef-flash routes") | $0.021 | **$21** |
| Clef / OpenRouter Prime Intellect route[[11]](https://openrouter.ai/cloudflare/clef "OpenRouter Clef routes") | $0.042 | **$42** |
| GLiDE / Fastino native[[21]](https://docs.fastino.ai/pricing "Fastino 定价") | $0.15 | **$150** |
| GLiNER-2.5-Decide / Fastino native[[21]](https://docs.fastino.ai/pricing "Fastino 定价") | $0.03 | **$30** |
| span-01 Pro / Respan native[[29]](https://www.respan.ai/docs/documentation/span-01/concept "Respan span-01 契约与报价") | $0.02 | **$20** |
| Aplomb 1 / EmpirioLabs native[[27]](https://docs.empiriolabs.ai/models/aplomb-1 "EmpirioLabs Aplomb 1 官方模型契约") | $0.02 | **$20** |
| Decider V1.1 27B / OpenRouter route[[36]](https://openrouter.ai/perplexity/pplx-decider-v1.1-27b "OpenRouter Perplexity Decider V1.1 27B") | $0.02 | **$20** |
| Solar Decide / OpenRouter promotional route[[35]](https://openrouter.ai/upstage/solar-decide "OpenRouter Solar Decide 当前 route") | $0.05 | **$50** |

### 相同模型也有明显的路线差价

Clef 在 Workers AI 原生为 $0.24/M 输入；OpenRouter 上 Cloudflare upstream 仍为 $0.24，Prime Intellect 为 $0.042。Flash 对应 $0.09 与 $0.021。Jev 原厂为 $0.042；Vercel 页面显示 $0.04，展示精度不足以证明真实 $0.002 折扣。默认路由或自动 fallback 都需要保留实际 provider。[[6]](https://developers.cloudflare.com/workers-ai/models/clef/ "Cloudflare Clef hosted schema")[[7]](https://developers.cloudflare.com/workers-ai/models/clef-flash/ "Cloudflare Clef-flash hosted schema")[[11]](https://openrouter.ai/cloudflare/clef "OpenRouter Clef routes")[[12]](https://openrouter.ai/cloudflare/clef-flash "OpenRouter Clef-flash routes")[[1]](https://docs.typesafe.ai/models "TypeSafe Jev 官方模型、上下文与报价")[[57]](https://vercel.com/ai-gateway/models/jev "Vercel Jev route 与显示报价")

Cloudflare 每日 10,000 Neurons 免费额度是 Workers AI 全平台共享；Respan Lite 有每日上限；Alibaba 当前北京、新加坡列为限时免费。把每个模型都视作独享一份免费额度会高估容量。[[8]](https://developers.cloudflare.com/workers-ai/platform/pricing/ "Cloudflare Workers AI 定价")[[29]](https://www.respan.ai/docs/documentation/span-01/concept "Respan span-01 契约与报价")[[30]](https://www.alibabacloud.com/help/en/model-studio/decision-model-preview "Alibaba Cloud decision-model-preview")

### F07 · 输入重复计费可以比单价更重要

纯算例：8,000-token state，10 个问题，每问 400 tokens。共享 state 只计一次是 12,000 tokens；每问重复 state 是 84,000 tokens，相差 7 倍。在相同 $0.05/M 下，费用分别为 $0.0006 与 $0.0042。Levanto 官方正好公开了后一种计数例子。它还按每个 tag、每个排序项重复计入内容；不能仅以“一个 batch”推断一次上下文费用。[[22]](https://levanto.ai/pricing "Levanto Sage 计费与套餐")

Fastino 的 usage 会累计内部各问题的输入 passes，GLiDE 输出 token 虽存在，当前输出费率为零。Liquid d1 的图片计费也需要按问题数核对。Levanto Sage 的答案免费，但 reasoning 为 $10/M output，搜索为每次 $0.10；输入单价 $0.038–0.05 还对应不同的预付套餐与额度。[[20]](https://docs.fastino.ai/inference/systemone "Fastino GLiDE System One 契约")[[21]](https://docs.fastino.ai/pricing "Fastino 定价")[[23]](https://docs.liquid.ai/lfm/models/d1.md "Liquid hosted d1")[[22]](https://levanto.ai/pricing "Levanto Sage 计费与套餐")

### 短标签任务的生成式对照

按 Luna 模型页 Standard 报价，设每次 1,000 input + 8 output、无缓存与思考，100 万次为 **$104**。Luna Decisions 基础输入报价下为 **$100**，此例 token 费用差约 ** 3.85%**。这只说明输出很短时，“输出免费”所省的部分很小；延迟、分布可得性、格式处理与真实输入开销仍可能影响整体价值。[[16]](https://developers.openai.com/api/docs/models/gpt-6-luna "GPT-6 Luna 模型级报价与上下文")[[14]](https://developers.openai.com/api/docs/guides/decisions "OpenAI Decisions guide")

生成式 Responses Batch 的相同算例是 $52，但它满足的是异步工作要求。当前所查 Batch 支持列表没有 Decisions；不能把模型页 Batch / Flex 折扣搬到 `/v1/decisions`。地区 premium 和长上下文倍率同样需要留在预算中。[[17]](https://developers.openai.com/api/docs/guides/batch "OpenAI Batch 支持范围")[[14]](https://developers.openai.com/api/docs/guides/decisions "OpenAI Decisions guide")

### 筛选 → 升级的盈亏条件

设筛选费用为 Cscreen，升级比例为 e，强模型费用为 Cstrong。基本条件是 `C_screen + e × C_strong < C_strong`；同一比较还必须满足既定质量和响应时间目标。继续沿用上述纯算例：Jev 全量筛选 $42，强模型直接调用 $104，则：

纯算例：100 万次请求，筛选 $42，直接强模型 $104；负节省表示更贵

| 升级至强模型的比例 | 筛选 + 升级总费用 | 相对直接调用的节省 |
| --- | --- | --- |
| 0% | $42 | 59.6% |
| 25% | $68 | 34.6% |
| 50% | $94 | 9.6% |
| 75% | $120 | -15.4% |
| 100% | $146 | -40.4% |

盈亏平衡为升级率约 59.6%。还未计入预处理、重复请求、检索、恢复、存储、出网及人工复核。生产指标应至少包含 **总支出 / 成功处理案例、升级率、最终任务质量、p50/p95 端到端延迟**。计算脚本与全部假设包含在证据包内；此处没有将算例当作运行账单。

## 05 · 本轮实做：公开历史预测复算

从 `David-DL-Space/sys1-eval` 提取稳定 ID、作者标签、候选数量和四份原始 / 翻转预测；没有重新运行 Jev 或 Laya。独立标准库 Python 程序重算准确率、改变答案数、高概率错误数，并与作者汇总对照。保留 1,000 个案例，合计 4,000 份预测，14 项对照检查全部吻合。原始文件 blob SHA、投影说明和数据哈希随包提供。[[41]](https://github.com/David-DL-Space/sys1-eval "sys1-eval 原始预测、构造与分析仓库")

独立离线复算 · 历史公开预测与作者标签；没有新推理调用

| 子集 | 模型 | 原始答对 / 案例 | 原始准确率 | Wilson 95% 区间 | maxP ≥ 0.9 中错误 / 入选 |
| --- | --- | --- | --- | --- | --- |
| A · 历史模型路由 | Jev（历史运行） | 200 / 400 | **50%** | 45.1%–54.9% | 184 / 375 |
| A · 历史模型路由 | Laya English（历史运行） | 194 / 400 | **48.5%** | 43.6%–53.4% | 1 / 1 |
| B · 随机干扰工具选择 | Jev（历史运行） | 398 / 400 | **99.5%** | 98.2%–99.9% | 0 / 391 |
| B · 随机干扰工具选择 | Laya English（历史运行） | 336 / 400 | **84%** | 80.1%–87.3% | 15 / 185 |
| F · 高候选数 / 多语言单选 | Jev（历史运行） | 162 / 200 | **81%** | 75%–85.8% | 10 / 136 |
| F · 高候选数 / 多语言单选 | Laya English（历史运行） | 70 / 200 | **35%** | 28.7%–41.8% | 48 / 96 |

**区间口径：** Wilson 95% 区间仅是这些选定子集的描述性二项区间；未针对来源聚类或样本选择作调整，也不构成生产风险保证或当前服务的总体准确率区间。

**模型和输入条件。** Jev 为历史 `jev-1.13.0`，Laya 为研究中的 English checkpoint。B 使用 BFCL simple / live\_simple，候选数 2、5、10、20、50 各 80 例，干扰工具随机采样。F 为 BANKING77 100 例、MASSIVE 10 种语言各 10 例，分别 77 / 60 个候选；这是单选意图分类。它不能单独证明当前中文、多标签或多模态性能。

**路由标签的实际含义。** A 用历史 RouterBench 的 Mistral-7B-chat 与 GPT-4-1106-preview 成绩定义 gold，均衡选择 200 个 cheap 与 strong 均合格、200 个仅 strong 合格案例。给模型的候选描述只有“小而快的 7B / frontier”泛称，17/400 条输入清理后截至 1,500 字符。因此接近 50% 的结果描述的是这个任务设定；它提示路由需要实际目标模型的能力信息，不能推广成所有决策模型都无法做模型路由。

### 顺序敏感性：复算数值之外还检查干预

| 较干净的单变量子集 | Jev 改变答案 | Laya 改变答案 |
| --- | --- | --- |
| B 工具选择，400 例 | 0 / 400 · 0% | 76 / 400 · 19% |
| F 高候选数 / 多语言单选，200 例 | 17 / 200 · 8.5% | 106 / 200 · 53% |

A 的翻转脚本同时删掉原请求中的 difficulty 问题，只留下 route。全体 1,000 例的答案变化率 1.8% / 30.3% 虽然能重算出来，A 及全体汇总不能全部归因于选项顺序。证据包把该混杂单独标出。[[42]](https://github.com/David-DL-Space/sys1-eval/blob/main/scripts/build_flip_large.mjs "sys1-eval 顺序干预生成脚本")

### F08 · 高概率筛选需要按任务验证

同一历史 Jev，A 中最高候选概率 ≥0.9 的 375 个答案有 184 个错误；B 中同样筛出的 391 个答案有 0 个错误。此处全都直接使用返回的候选概率，4,000 份记录均有完整 probabilities。这个反差足以否定将“0.9”无条件当作跨任务正确率的做法，却不足以估计当前服务在新任务上的校准。下一步有效验证应在自己的任务上画风险—覆盖率曲线，并独立选择阈值。

## 06 · 六组论文与实践怎样相互校验

| 原始研究 / 实践 | 可用证据与本轮工作 | 对采用判断的贡献 |
| --- | --- | --- |
| Fast Models, Slow Evidence | 作者 11 决策点评测；本轮独立复算 3 个 Choice 子集，并读输入构造 / 干预 / 成本代码 | 区分任务、接口干预和端到端收益 |
| 37 数据集 Jev benchmark | 作者 346,009 次请求；本轮审读冻结模板、阈值代码与汇总，未复算全部请求 | 报告分任务校准；开发集调阈值后在固定测试集评估 |
| 七项政治学复现 | 论文方法、表格、原作者澄清；未找到可直接获取的复现档案链接 | 生成式 Batch 是批处理任务的真实成本对照；阅读与记忆任务分开 |
| winnow context sieve | 审读问题构造、保留 / 隐藏 / 恢复策略和标签来源 | 可回取原文、影子运行与低概率尾部审计 |
| Agent security selective automation | 作者测试集及阈值分析；本轮读分区检查和选择代码 | 分别报告自动允许、自动阻止和升级；看错误互补性 |
| Crash narrative coding | 作者规模化编码；本轮读抽样加权、成本模型和汇总 | 问题 schema 开销、样本单位、实跑费用与总体外推分开 |

**阈值可能改变结论。** 37 数据集研究的 UNFAIR-ToS micro-F1 从约 0.499 提升到 0.748，模型未变，变化来自开发集上选取各问题阈值。作者在 22 个 Choice 数据集上报告 pooled ECE 0.028、平均每数据集 ECE 0.061；大数据集会改变汇总权重。正文结论和此处数字来自作者结果，本轮只核对了相关代码与聚合文件。[[43]](https://arxiv.org/html/2609.37647v1 "Evaluating and Benchmarking the System One Model Jev")[[44]](https://github.com/AppliedMachineLearning-Lab/jev-benchmarking "37 数据集评测与阈值选择实现")

**论文发表时间与接口发布时间需要对齐。** 政治学研究比较了 Jev、普通生成式 Luna 和 Qwen。作者明确说明尚未测试 10 月 6 日发布的 OpenAI Decisions API。因此它可以说明短答案、Batch 和概率来源如何影响比较，无法给出当前 Jev 与新 Decisions endpoint 的胜负。[[45]](https://arxiv.org/abs/2610.06625 "JEV versus LLMs · 七项政治学复现")[[46]](https://www.pixelsandpatterns.org/p/jev-is-fast-is-it-better-than-llms "原作者方法与新 Decisions endpoint 澄清")[[18]](https://developers.openai.com/api/docs/changelog "OpenAI changelog：2026-10-06 Decisions public beta")

**标签名称需要追到实际标注流程。** winnow 中标作 “hand” 的 97 个可判定的模型辅助标签，原始说明显示由 Claude 标注。结构化措辞在所隐藏的 23 个文本块中未出现被该标注判为需要的块；样本小且为概率分层，不能写成人工验证的零漏删保证。它的工程价值在于保留不确定内容、原文可回取以及策略可回放。[[48]](https://github.com/GhalebDweikat/winnow/blob/main/docs/DESIGN.md "winnow 原始设计、标签和失败分析")[[49]](https://github.com/GhalebDweikat/winnow/blob/main/sidecar/src/winnow/policy.py "winnow 执行策略")

**端到端成本会修正标题数字。** sys1-eval 自审指出，一条安全筛选链漏计前筛开销时显示约 23.9% 节省，加回后约 4.3%。交通事故研究实际完整编码 195,857 份叙述，该完整编码阶段费用为 $30.22；此前还筛选了 499,500 份。约 $774 是对 5,018,080 份总体完整编码的外推。用量阶段、成本口径和样本单位必须跟随每个数字。[[40]](https://arxiv.org/abs/2610.02267 "Fast Models, Slow Evidence · 2026-10-01 v1")[[52]](https://arxiv.org/abs/2609.24052 "Calibrated Decisions at Scale · crash narratives")[[53]](https://github.com/pozapas/jev-calibrated-narrative-coding "Crash narrative 编码、加权评估与成本实现")

**安全分类的覆盖率需要按动作拆开。** 安全研究在 1% miss-limit 设置下选取独立 allow / block 阈值，某个 Jev 策略在 WAInject 测试中只自动阻止 108/1,612 项，自动允许为零。仓库审计说明披露，部分阈值敏感性分析在初次查看测试集后补做，因此属于回顾性分析。这个例子支持分别核对 allow、block 与 review 的误差，并验证第二模型是否真的能纠正第一模型的错误。[[50]](https://arxiv.org/abs/2609.33401 "System One Agent Security Evaluation · v3")[[51]](https://github.com/yxsec/system-one-security-eval "Security evaluation 阈值与分区实现")

六项研究的详细模型、日期、样本、标签、代码文件和局限整理于 `practice_evidence.json`。原作者报告的时延、成本和准确率没有拼成一个跨任务总榜。

## 07 · Repositories：按可复用部分阅读

仓库数量不能直接反映可替代模型数量。一个 repo 可能只是 SDK、服务包装或评测；同一 checkpoint 也可能被多个 runtime 接入。优先看模型文件、实际推理函数、概率计算、限制、许可及失败路径。以下表格保留具体可复用部件与本轮证据深度。

21 个仓库 · 运行时、模型、SDK、适配与评测分别登记

| 仓库 | 角色 | 可复用机制 | 本轮审读深度 | 许可范围 / 限制 |
| --- | --- | --- | --- | --- |
| [NandhaKishorM/laya](https://github.com/NandhaKishorM/laya)[[59]](https://github.com/NandhaKishorM/laya "Laya 原作者仓库")[[93]](https://github.com/NandhaKishorM/laya/blob/3cf26cbcb18725dbc2d127bb8bb2c4c43243ae63/laya/confidence.py "laya_confidence")[[123]](https://github.com/NandhaKishorM/laya/blob/3cf26cbcb18725dbc2d127bb8bb2c4c43243ae63/tests/test_conformal_abstention.py "Checks invalid/unreachable bucket keys and end-to-end gating when confidence is histogram-recalibrated, including coverage loss from global thresholds.") | 模型 + runtime | 校准、confidence、按题型 / 候选数分桶 abstention | 固定 revision 源码 / 测试定义已读 | Apache-2.0 per repo/model |
| [jaredpalmer/kev](https://github.com/jaredpalmer/kev)[[95]](https://github.com/jaredpalmer/kev "kev_repo")[[124]](https://github.com/jaredpalmer/kev/blob/5e42a7a03f28134853dd3ff77461457e921e5ec1/kev/model.py "PointerHead explicitly divides inference logits by fitted checkpoint temperature; ContextOverflow and admission separate training/serving budgets; branch mask isolates question branches.")[[125]](https://github.com/jaredpalmer/kev/blob/5e42a7a03f28134853dd3ff77461457e921e5ec1/tests/test_model.py "Tests merged/unmerged LoRA parity, prefix-cache/full-pass parity and cache reuse, state/branch overflow, row batching versus packed outputs with numeric tolerances.") | 模型 + 训练 / serving | pointer head、共享前缀、优化路径概率一致性 | 固定 revision 源码 / 测试定义已读 | Apache-2.0, dataset terms separate |
| [togethercomputer/tev1](https://github.com/togethercomputer/tev1)[[94]](https://github.com/togethercomputer/tev1 "tev_repo")[[126]](https://github.com/togethercomputer/tev1/blob/main/examples/decide.py "Validates2–24options; sets temperature0,max_tokens8,logprobs/top_logprobs5 and disables thinking. Parses answer letter via select().") | 模型 + 参考推理 | next-token 字母分类、Chat Completions 参考实现 | decide.py / 模型卡；权重许可待定 | Code MIT; model-card weight license not finalized |
| [ozlabsai/typical](https://github.com/ozlabsai/typical)[[96]](https://github.com/ozlabsai/typical "typical_repo")[[127]](https://github.com/ozlabsai/typical/blob/main/inference/test_parity.py "Tests cache expansion versus deepcopy and non-aliasing; compares public inference wrapper against internal decider; reverses Noul labels and tests invariant probabilities. Preview uses different Choice head path.")[[97]](https://github.com/ozlabsai/typical/blob/main/releases/typical-small.md "typical_release") | 模型 + inference | state cache、factored null、Noul 不变性 | parity 测试定义 / release notes | Release notes labelweightsApache2 but explicitly flag uncertain and non-commercial training-source terms |
| [bespokelabsai/nimble](https://github.com/bespokelabsai/nimble)[[101]](https://github.com/bespokelabsai/nimble "nimble_repo")[[128]](https://github.com/bespokelabsai/nimble/blob/main/nimble/scoring/parallel_scorer.py "Implements three evaluation modes and explicit candidate projection; warns cache broadcasting can allocate and stock append may materialize batch arrays.")[[129]](https://github.com/bespokelabsai/nimble/blob/main/tests/test_parallel_scorer.py "Tests unequal suffix-length parity, microbatch/one-field behavior, cache not mutated by branches and candidate-only versus full projection.") | 模型 + runtime | 候选投影、并行后缀、不污染缓存 | 源码 / 测试定义；demo 另列 | Apache-2.0 model |
| [Yinsongxu/LLM2Jev](https://github.com/Yinsongxu/LLM2Jev)[[61]](https://github.com/Yinsongxu/LLM2Jev "Yinsongxu/LLM2Jev")[[130]](https://github.com/Yinsongxu/LLM2Jev/blob/main/examples/valen_sokoban_single_step.py "Single-step evaluator gathers backend yes_probabilities per candidate, L1-normalizes and chooses argmax; supports option rotations/ensembling, tie-aware optimal action targets, legality and push metrics.")[[131]](https://github.com/Yinsongxu/LLM2Jev/blob/main/README.md "Declares backend support/HTTP endpoint and separate single-step500-questionSokoban evaluation; includesunittestentrypoint.") | 通用模型适配 | 逐候选 yes/no 后归一；视觉动作等价解评估 | 原作者示例代码已读 | Apache-2.0 |
| [tic-top/llm2jev](https://github.com/tic-top/llm2jev)[[62]](https://github.com/tic-top/llm2jev "tic-top/llm2jev")[[132]](https://github.com/tic-top/llm2jev/blob/main/llm2jev/backends.py "HF/MLX read last-position logits; vLLM chunks requested token IDs when sets exceed chunk size, reusingprefix; media uses different endpoint; backend-specific actual prefill can differ.")[[133]](https://github.com/tic-top/llm2jev/blob/main/scripts/parity.py "Compares exact rendered prompts againstTransformer reference using logprob gap, probability gap andargmax; includes image/video/audio probes; exits nonzeroonfail.") | 通用模型适配 | 单位置候选 token softmax；backend / media parity | 后端代码 / parity 脚本已读 | MIT per repo |
| [ollaya-dev/ollaya](https://github.com/ollaya-dev/ollaya)[[134]](https://github.com/ollaya-dev/ollaya "ollaya-dev/ollaya")[[135]](https://github.com/ollaya-dev/ollaya/blob/main/crates/ollaya-decision/src/lib.rs "Enumerates separate model-family implementations, typed question parsing, calibration and head budget errors; repository existence is not proof each backend currently works.")[[136]](https://github.com/ollaya-dev/ollaya/blob/main/crates/ollaya-decision/src/answer.rs "One distribution has two namedconfidence projections:normalizedtopprobabilityforTypeSafe=(K*pmax−1)/(K−1);normalizedentropyforLaya=1−H/logK. Scoreisexpectedindex; mapswirefields.")[[137]](https://github.com/ollaya-dev/ollaya/blob/main/docs/api.md "Documentsdaemon API/model management andengineconstraints; READMEdescribesexport parity/goldenfixturepipeline.") | 模型管理 / runtime | 权重谱系、ONNX / GGUF、协议投影 | Rust 回答层已读 | Apache-2.0 runtime; every bundled/referencedmodel retainsownlicense |
| [fastino-ai/GLiNER2](https://github.com/fastino-ai/GLiNER2)[[138]](https://github.com/fastino-ai/GLiNER2 "fastino-ai/GLiNER2")[[139]](https://github.com/fastino-ai/GLiNER2/blob/main/gliner2/auto.py "Registry-based architecture dispatch with UnknownArchitecture/ArchitectureMismatcherrors and model-loadingkwargsvalidation.")[[140]](https://github.com/fastino-ai/GLiNER2/blob/main/gliner2/models/span/model.py "ConcreteSpanExtractorModel implementation and structured forward/loss branches; legacygliner2/model.pyisashim,notdecisionlogic.")[[141]](https://huggingface.co/fastino/GLiNER2.5-Decide/blob/main/README.md "Describes English340MDecide, single-label versus thresholdmultilabel andspecializedoperationaltasks.") | schema 分类 / 提取 | 模型架构分发、encoder、多标签分类 | AutoExtractor / 具体实现已读 | GLiNER2.5-DecideweightsApache2; code license not separatelyread |
| [GhalebDweikat/winnow](https://github.com/GhalebDweikat/winnow)[[47]](https://github.com/GhalebDweikat/winnow "winnow 实践与仓库")[[142]](https://github.com/GhalebDweikat/winnow/blob/main/hooks/winnow.ts "Hook interceptsandforwardstoolresult,asks sidecar tofilterlargeoutputsandaddscontextatprompttime;sharedrestart/backofflogicpresent.")[[143]](https://github.com/GhalebDweikat/winnow/blob/main/tests/winnow.test.ts "Tests unreachable sidecar passesoriginaltoolresult unchanged,smallresultanddeniedcallpass-through,promptunchangedwhenunreachable,coalescedrestartandbackoff.")[[144]](https://github.com/GhalebDweikat/winnow/blob/main/README.md "Replay/labelcommands and discussioncalibrationplusdiscrimination; shadow/activeoperation andrecall controls.") | 下游工作流 | shadow、回放、原文 recall、hook 失效处理 | hook / policy / 模型辅助标签来源已读 | Repo license file not separatelyread in this stream |
| [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp)[[37]](https://github.com/ggml-org/llama.cpp/releases/tag/v0.6.0 "llama.cpp v0.6.0 正式发行")[[38]](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md "llama.cpp 当前 server API 文档")[[39]](https://github.com/ggml-org/llama.cpp/pull/29969 "llama.cpp Clef vision 已合并 PR") | 本地 runtime | 原生 System One、Clef 图像、joint schema | 正式发行 / 当前文档 / merged PR | 模型各自许可；runtime 许可见原仓库 |
| [typesafe-ai/typesafe-sdk-python](https://github.com/typesafe-ai/typesafe-sdk-python)[[83]](https://github.com/typesafe-ai/typesafe-sdk-python "Official Python SDK, MIT") | 原厂 SDK | 同步 / 异步、typed answers、重试、HTTP/2 | README / 原厂代码资料审读 | MIT 客户端；不含 Jev 权重 |
| [typesafe-ai/typesafe-sdk-js](https://github.com/typesafe-ai/typesafe-sdk-js)[[84]](https://github.com/typesafe-ai/typesafe-sdk-js "Official JS/TS SDK, MIT") | 原厂 SDK | 由 questions 推断答案类型 | README / 类型接口资料审读 | MIT 客户端 |
| [typesafe-ai/system-one-adapter-python](https://github.com/typesafe-ai/system-one-adapter-python)[[55]](https://github.com/typesafe-ai/system-one-adapter-python "TypeSafe System One adapter for ordinary LLMs") | 生成模型对照 | 普通 LLM 接入问题契约；重试与原始输出 | 相关代码 / 说明已读 | MIT |
| [typesafe-ai/WorkflowEvals](https://github.com/typesafe-ai/WorkflowEvals)[[54]](https://github.com/typesafe-ai/WorkflowEvals "TypeSafe WorkflowEvals") | 工作流评测 | 版本、恢复、参考模型、usage、缺价处理 | README / 工作流结构审读 | Apache-2.0 代码；数据各自来源 |
| [typesafe-ai/typesafe-public-examples](https://github.com/typesafe-ai/typesafe-public-examples)[[56]](https://github.com/typesafe-ai/typesafe-public-examples "TypeSafe 原厂实践代码") | 原厂实践 | fan-out、RAG passage 示例 | 原厂归属 / 结构确认 | MIT |
| [openai/openai-python](https://github.com/openai/openai-python)[[117]](https://github.com/openai/openai-python/blob/main/src/openai/resources/decisions.py "source inspected")[[118]](https://github.com/openai/openai-python/blob/main/src/openai/types/decision_create_params.py "source inspected")[[119]](https://github.com/openai/openai-python/blob/main/src/openai/types/decision.py "source inspected") | 原厂 SDK | Decisions 请求类型、refusal、响应类型 | 资源 / 类型文件；已记录 blob SHA | 本轮未单独审阅许可证文件 |
| [David-DL-Space/sys1-eval](https://github.com/David-DL-Space/sys1-eval)[[41]](https://github.com/David-DL-Space/sys1-eval "sys1-eval 原始预测、构造与分析仓库") | 比较评测 | 成对输出、输入构造、顺序干预、成本 | 源码 + 1,000 案例独立离线复算 | MIT 代码；输出 / 底层数据另列 |
| [AppliedMachineLearning-Lab/jev-benchmarking](https://github.com/AppliedMachineLearning-Lab/jev-benchmarking)[[44]](https://github.com/AppliedMachineLearning-Lab/jev-benchmarking "37 数据集评测与阈值选择实现") | 公开任务评测 | 冻结模板、hash cache、阈值 / 测试分开 | 相关源码 / 汇总已读 | MIT 代码；响应另有 Jev Responses License |
| [yxsec/system-one-security-eval](https://github.com/yxsec/system-one-security-eval)[[51]](https://github.com/yxsec/system-one-security-eval "Security evaluation 阈值与分区实现") | 选择性自动化 | allow / block 阈值、分区、错误互补性 | 阈值代码 / 汇总 / 审计说明 | 本轮未单独审阅许可证文件 |
| [pozapas/jev-calibrated-narrative-coding](https://github.com/pozapas/jev-calibrated-narrative-coding)[[53]](https://github.com/pozapas/jev-calibrated-narrative-coding "Crash narrative 编码、加权评估与成本实现") | 规模化领域实践 | 抽样加权、分阶段成本、总体外推 | 指标 / 成本代码 / 汇总已读 | 原始叙述不随包公开；仅审代码 / 汇总 |

### 四个特别值得分辨的实现关系

**Clef + llama.cpp。** 正式 v0.6.0 发行与已合并视觉 PR 确认 System One 文本 / 图片路线；当前 server 文档要求图像 projector，Clef 整个 prompt 要放进物理 batch，`--ubatch-size` 也影响可处理长度。只增大 context 参数不足以证明同等有效输入。当前 master 的字段不能全部追溯为 v0.6.0 的行为。本轮未执行模型，也未逐行审完 C++ 实现。[[37]](https://github.com/ggml-org/llama.cpp/releases/tag/v0.6.0 "llama.cpp v0.6.0 正式发行")[[38]](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md "llama.cpp 当前 server API 文档")[[39]](https://github.com/ggml-org/llama.cpp/pull/29969 "llama.cpp Clef vision 已合并 PR")

**Tev 与候选概率。** Together Tev1 使用保留 next-token head 的模型，实验模型卡及代码需要与专门 joint decision head 区分。候选条件化概率是否覆盖多 token label、如何归一化、是否只允许 A/B/C 字母，都是适配器需要确认的部分。[[60]](https://huggingface.co/togethercomputer/Tev1-4B-experimental "Together Tev1-4B-experimental 模型卡")

**两个 LLM2Jev。**`Yinsongxu/LLM2Jev` 与 `tic-top/llm2jev` 是不同项目；前者强调 prefill 与分支前缀复用，多种后端，后者另有兼容运行路径。一个项目报告的本地硬件时延与远程 Jev 网络时延不能直接当作模型快慢总排名。[[61]](https://github.com/Yinsongxu/LLM2Jev "Yinsongxu/LLM2Jev")[[62]](https://github.com/tic-top/llm2jev "tic-top/llm2jev")

**研究标签与工作流参考。** TypeSafe WorkflowEvals 很适合学习 revision、恢复运行、完整响应、价格缺失处理和工作流评测组织；其参考模型一致度需要与人类真值区分。原厂 adapter 中由生成模型写出的概率，也不能因格式化和归一化自动视为已校准概率。[[54]](https://github.com/typesafe-ai/WorkflowEvals "TypeSafe WorkflowEvals")[[55]](https://github.com/typesafe-ai/system-one-adapter-python "TypeSafe System One adapter for ordinary LLMs")

## 08 · 可迁移的工作流实践

| 任务 | 推荐的结构 | 真正要验证的量 |
| --- | --- | --- |
| 工单 / 内容 / 工具分流 | 明确定义选项，允许 unknown；把判断与执行分开，记录完整分布 | 每类召回、近似候选混淆、拒绝率、失败率、单位成功成本 |
| 选择便宜 / 强模型 | 用实际目标模型的输出质量建立标签与能力描述，再做校准和升级策略 | 最终答案质量、升级率、两级总成本、尾延迟 |
| RAG relevance / context 筛选 | 记录检索候选与段落 ID，保留原文和恢复路径；先做离线回放与 shadow | 关键证据召回、最终答案质量、恢复频率、筛选后完整 token 账 |
| 长文档 rubric / 信息核验 | 等级定义具体化；缺失、矛盾、未知单列；精确金额与日期由代码校验 | 首尾证据、跨段引用、等级分布、错误集中在哪些文本类型 |
| Agent traces / 行为观测 | 按明确行为定义判断，保留不可观测状态；把上下文与被评分输出分开 | 不同 trace 长度 / 语言 / 行为的 F1、误警和未知率 |
| 高代价分支与安全检测 | 代码约束与多级复核；允许、阻止分别选阈值；失效状态有明确路线 | 各动作分母下的错误、独立样本数、复核子集错误相关性 |

上述结构综合原作者 cookbook 与所审实践形成。RAG cookbook 明确其分类器不构成独立安全边界；winnow 示范了可恢复过滤；Respan 为不可观测提供原生分布；安全研究说明“再叫一个更强模型”仍需要评估两个阶段错误是否互补。[[58]](https://docs.typesafe.ai/cookbooks/classifying_rag_passages "TypeSafe RAG passage classification cookbook")[[49]](https://github.com/GhalebDweikat/winnow/blob/main/sidecar/src/winnow/policy.py "winnow 执行策略")[[29]](https://www.respan.ai/docs/documentation/span-01/concept "Respan span-01 契约与报价")[[50]](https://arxiv.org/abs/2609.33401 "System One Agent Security Evaluation · v3")

### 一份有效的比较记录应包含什么

每次保留输入内容哈希、schema、选项顺序、问题 key、模型与返回版本、实际 route、地区、SDK / runtime、完整原始回答、usage、时间、重试、失败状态、阈值版本与标签来源。模型 schema 验证通过、任务答对、概率校准、最终工作流成功是四项不同指标。

为每个真实任务建立互不泄漏的开发、阈值选择和测试数据；按相同来源文档 / 会话 / 实体分组拆分。不同候选数、语言、缺少证据、边界条件、长输入和对抗内容分别报告。跨供应商先适配语义再比较，同一阈值通常不能直接搬用。固定阈值与固定可接受错误下的覆盖率，都值得保留；不能只看平均 ECE。

中文使用尤其需要自己的等义中英与混合语言任务集。多语言平均分不能取代中文领域判断；对否定、时间顺序、条件例外、近义部门、专名和中英 code-switching 应单独留记录。Jev 原厂已披露语言与数值等能力的参差，公开历史研究的中文样本也不足以支撑跨厂商中文总排名。[[5]](https://docs.typesafe.ai/model-jaggedness/jev-1.13 "Jev 1.13 已知能力边界")[[41]](https://github.com/David-DL-Space/sys1-eval "sys1-eval 原始预测、构造与分析仓库")

12 项原创公开探测协议 · 方法草案，尚未调用 API

| 检查 ID | 项目 | 方法与结论边界 | 状态 / 依据 |
| --- | --- | --- | --- |
| P01\_BASELINE | 基线与重复性 | 6 个原创文本样例；参考标签是人工目标，不是模型承诺。 | NOT RUN |
| P02\_CHOICE\_ORDER | Choice 顺序 | 同一选项 ID / 描述重排；除已核具体路径外，只观察差异。 | NOT RUN[[5]](https://docs.typesafe.ai/model-jaggedness/jev-1.13 "Jev 1.13 已知能力边界")[[10]](https://huggingface.co/Cloudflare/clef-flash/blob/41318bf2106d135c7a92da745fec4b255279b4de/joint_schema_model.py "Clef-flash 固定 revision Python helper") |
| P03\_QUESTION\_ID | Question ID 重命名 | 仅原生 Jev 的 key 不进入推理承诺构成对应检查。 | NOT RUN[[2]](https://docs.typesafe.ai/api "TypeSafe System One API 契约")[[10]](https://huggingface.co/Cloudflare/clef-flash/blob/41318bf2106d135c7a92da745fec4b255279b4de/joint_schema_model.py "Clef-flash 固定 revision Python helper") |
| P04\_APPEND\_UNRELATED | 追加无关问题 | Jev 文档承诺问题隔离；Clef 联合求值只作观察。 | NOT RUN[[4]](https://docs.typesafe.ai/introduction "Jev 多问题隔离语义")[[63]](https://blog.cloudflare.com/clef-decision-models/ "Cloudflare original launch; architecture, training and internal domain-classification practice")[[38]](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md "llama.cpp 当前 server API 文档") |
| P05\_SINGLE\_VS\_BUNDLED | 单问与多问打包 | 分别核验输出、usage 与计费，不推定共享前缀免费。 | NOT RUN[[4]](https://docs.typesafe.ai/introduction "Jev 多问题隔离语义")[[1]](https://docs.typesafe.ai/models "TypeSafe Jev 官方模型、上下文与报价") |
| P06\_BILINGUAL | 中英等义任务 | 预期语义标签相同；不承诺跨语言概率相同。 | NOT RUN[[1]](https://docs.typesafe.ai/models "TypeSafe Jev 官方模型、上下文与报价") |
| P07\_EXPLICIT\_UNKNOWN | 缺少证据 / 显式 unknown | 显式提供 unknown；与低 confidence、否定回答分开。 | NOT RUN[[69]](https://docs.typesafe.ai/primitives/choice "255 option maximum and explicit none-of-the-above practice")[[3]](https://docs.typesafe.ai/confidence "Jev confidence 定义")[[71]](https://docs.typesafe.ai/primitives/noul "Proposition probability; not degree/intensity") |
| P08\_CONTEXT\_POSITION | 长上下文首尾证据 | 固定内容、改变位置；截断和溢出不得混为顺序效应。 | NOT RUN[[1]](https://docs.typesafe.ai/models "TypeSafe Jev 官方模型、上下文与报价")[[7]](https://developers.cloudflare.com/workers-ai/models/clef-flash/ "Cloudflare Clef-flash hosted schema")[[12]](https://openrouter.ai/cloudflare/clef-flash "OpenRouter Clef-flash routes")[[38]](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md "llama.cpp 当前 server API 文档") |
| P09\_OUTPUT\_CONTRACT | 类型、概率与 confidence | 按各 route 文档核对，不套用通用 confidence 公式。 | NOT RUN[[2]](https://docs.typesafe.ai/api "TypeSafe System One API 契约")[[3]](https://docs.typesafe.ai/confidence "Jev confidence 定义")[[71]](https://docs.typesafe.ai/primitives/noul "Proposition probability; not degree/intensity")[[10]](https://huggingface.co/Cloudflare/clef-flash/blob/41318bf2106d135c7a92da745fec4b255279b4de/joint_schema_model.py "Clef-flash 固定 revision Python helper") |
| P10\_SCORE\_MEAN\_MODE | Score 期望与众数 | 纯数学例子 [0.4,0.1,0.5]：期望 1.1，众数 2。 | NOT RUN[[70]](https://docs.typesafe.ai/primitives/score "Ordinal scoring primitive")[[38]](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md "llama.cpp 当前 server API 文档") |
| P11\_REFUSAL\_AND\_INVALID | 语义拒绝、错误与无效输出 | 区分正常分类、unknown、refusal、HTTP error 与解析失败。 | NOT RUN[[2]](https://docs.typesafe.ai/api "TypeSafe System One API 契约")[[70]](https://docs.typesafe.ai/primitives/score "Ordinal scoring primitive")[[38]](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md "llama.cpp 当前 server API 文档") |
| P12\_INLINE\_IMAGES | Inline image 路由约束 | 按 schema、编码和 projector 检查；接受输入不等于读到图像。 | NOT RUN[[7]](https://developers.cloudflare.com/workers-ai/models/clef-flash/ "Cloudflare Clef-flash hosted schema")[[13]](https://openrouter.ai/docs/guides/community/multimodal-decisions "OpenRouter 多模态 Decisions 契约与样例")[[1]](https://docs.typesafe.ai/models "TypeSafe Jev 官方模型、上下文与报价")[[38]](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md "llama.cpp 当前 server API 文档") |

## 09 · 选型收束与仍待解决的问题

**需要成熟的公开概率契约与参考实践：** 把 Jev 纳入基准；其原厂文档对问题语义和已知弱点的披露较充分。**需要图片与可审阅本地模型：** 优先比较 Clef 的原生、网关和 llama.cpp 路线，并另看 Liquid 开放版本。**已使用 OpenAI 且要原生封闭判断：** 将新 Decisions endpoint 放入同任务试验，保留 public beta 和 endpoint 级限制。以上是基于契约与工程路径的入围建议，质量名次尚待同任务实测。[[2]](https://docs.typesafe.ai/api "TypeSafe System One API 契约")[[5]](https://docs.typesafe.ai/model-jaggedness/jev-1.13 "Jev 1.13 已知能力边界")[[9]](https://huggingface.co/Cloudflare/clef-flash "Cloudflare Clef-flash 模型卡")[[38]](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md "llama.cpp 当前 server API 文档")[[25]](https://docs.liquid.ai/lfm/models/d1-3b.md "Liquid d1-3B 文档")[[14]](https://developers.openai.com/api/docs/guides/decisions "OpenAI Decisions guide")

**要在数据仓库内做批量业务判断：** Databricks ai\_decide 的治理与 SQL 路径有独立价值，应比较整条数据处理账单和支持区域。**要中文云入口：** Alibaba decision-model-preview 与腾讯 Makers 的 Jev 接入值得分别核验原生模型、转售路线、免费条件和数据处理边界。**要 trace 行为判断：** Respan 的不可观测状态更贴近该任务；Aplomb 的 abstain、受限 tool 参数和多模态属于值得单独探测的扩展契约。[[32]](https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_decide "Databricks ai_decide SQL 契约")[[30]](https://www.alibabacloud.com/help/en/model-studio/decision-model-preview "Alibaba Cloud decision-model-preview")[[29]](https://www.respan.ai/docs/documentation/span-01/concept "Respan span-01 契约与报价")[[27]](https://docs.empiriolabs.ai/models/aplomb-1 "EmpirioLabs Aplomb 1 官方模型契约")

| 未决项 | 当前能说到哪里 | 什么证据会解决它 |
| --- | --- | --- |
| 当前跨供应商准确率 / 中文表现 | 已有多项历史研究；没有本轮统一推理结果 | 固定任务、标签、版本和 route 的成对测试 |
| 生产 p95 / 并发 / 失败率 | 厂商资料与作者特定环境测量 | 同地区、同输入、冷热与并发分层测量 |
| 概率校准 | 某些公式与历史任务结果已知 | 独立任务标签、可靠性曲线、风险—覆盖率与分组审计 |
| Clef hosted 有效 state 和 confidence | 原厂、网关与本地路径存在未对齐描述 | 路径固定的首尾探针与实际原始回答 / 官方澄清 |
| 部分产品底层模型身份 | 服务别名 / 公开归属可核；训练来源未公开 | 模型卡、固定 checkpoint、返回版本与原厂说明 |
| 企业价格、区域、数据保留与 SLA | 仅记录可核实的公开条款；未做采购级比较 | 具体账户和合同；保持功能测试与商业条款独立 |
| “全面”覆盖 | 多入口 census，别名与 route 去重，另列 watchlist | 补充遗漏的原厂来源并按同一字段增量核验 |

维护时优先更新会改变结论的字段：版本别名、实际 upstream、收费单位、免费期限、模态与有效上下文、概率语义、运行时支持、模型许可。新的性能数字需要带上任务和方法，避免在旧表中只替换一个百分数。来源和数据结构可供任何读者复查；特定项目的权重、个人偏好和采购决定另写采用备忘录即可。

## 数据与复现入口

完整结构化记录和阅读顺序见 [本期说明](README.md)。来源记录见 [source_index.json](source_index.json)，待核线索见 [watchlist.json](watchlist.json)。历史逐条模型响应不随仓库分发；复算方法与输入条件见本期说明。
