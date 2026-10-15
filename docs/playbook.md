# 妙妙玩法大全 · Decisions Lab 配方册

**把有限选项的判断，变成可以反复试的玩法。** 本页收集 20 个具体玩法，分成 6 组。每个玩法都写清楚真实输入、有限选项（含补信息或 unknown 等出口）、能借哪个已存在项目的具体机制、第一次怎么试、常见失败以及何时交还给人。

事实真源是 [`catalog/recipes.json`](../catalog/recipes.json)；本页的输入、问题与选项与它保持一致。JSON 给首页取数据，本页负责把每条玩法讲清楚。当前版本日期 2026-10-15，项目证据日期逐条标注。

## 怎么读这本册子

- **玩法是本项目的提案，机制是别人已有的实现。** 每条玩法的 `project` / `mechanism` 指向一个真实存在的项目；把那个机制拿来用在什么场景上是我们的提案。两者必须分开看，不能把提案当成某个项目已经支持的功能。
- **两种状态。** `implemented-offline`：本仓库真实已有实现，可以先离线跑（目前只有 next-action 实验这两条）。`recipe`：可操作配方，但需要调用方自己实现，本仓库没有对应 CLI。
- **建议不自动执行。** 所有玩法都只产出建议；是否采纳、是否影响外部系统由人或调用方代码决定。
- **这不是穷尽市场。** 册子是"可以怎么用"的样例集合，不代表决策模型的全部用法，也不构成任何能力、价格或质量排名。

## 分组总览

| 分组 | 标题 | 条数 |
| --- | --- | --- |
| `reading-research` | 阅读与研究 | 3 |
| `dev-agent` | 开发与 agent | 3 |
| `knowledge` | 知识整理 | 3 |
| `creative-interactive` | 创作与互动 | 4 |
| `life-choice` | 生活与选择 | 2 |
| `reliability-lab` | 可靠性实验 | 5 |

## 现成项目怎么开始

想借哪条机制，直接从这些入口看起。表格描述的是各项目当前的说明；**本项目没有安装或运行它们**，命令来自各项目自己的文档，首次使用前请以仓库当前 README 为准。

| 项目 | 借来的机制 | 确切入口 | 首次是否下载 / 调用模型 | 能试哪条配方 |
| --- | --- | --- | --- | --- |
| [GhalebDweikat/winnow](https://github.com/GhalebDweikat/winnow) | 保留 error/uncertain 块、confidence-no 块可隐藏但有本地原文 recall、sidecar 不可达时原样透传 | README；`uv run --project winnow/sidecar winnow demo --fake` | `--fake` 走合成数据；去掉 `--fake` 会发真实 provider 调用。要求 Claude Code 2.1.260+ 的 function hooks | `dev-tool-output-triage` |
| [NandhaKishorM/laya](https://github.com/NandhaKishorM/laya) | router 选 checkpoint + typed choice + 分桶 abstention | README 与 `examples/README.md`（41 例、8 阶段路径）；`laya "…" --predict` | 只做 routing 不下载模型；加 `--predict` 才首次下载 checkpoint | `reading-paper-next-section`、`play-soundscape-switch`、`rel-abstention-buckets` |
| [typesafe-ai/WorkflowEvals](https://github.com/typesafe-ai/WorkflowEvals) | 版本固定、恢复运行、参考模型一致度、usage、缺价处理 | `uv sync --locked`（Python 3.13+）；`uv run python run.py invoice_processing --limit 5 --dry-run`；四个 workflow：invoice_processing / customer_service / agent_trace_observability / security_incidents | `--dry-run` 检查 input、不调模型，但可能下载 HF 数据 | `rel-replay-threshold-coverage` |
| [David-DL-Space/sys1-eval](https://github.com/David-DL-Space/sys1-eval) | 从已发布的原始输出复算（无需 API）；输入构造 / 顺序干预 / 成本分开 | `paper/analysis.py` | 复算本地原始输出，不发 API 调用 | `reading-repro-layers` |
| [typesafe-ai/typesafe-public-examples](https://github.com/typesafe-ai/typesafe-public-examples) | fan-out（并行多问、代码判断适用性）与 RAG passage 示例 | 根 README | 示例不打包模型；真实调用需按各自项目配置 | `know-fanout-questions`、`reading-passage-relevance` |

WorkflowEvals 的分数是**与 reference 的一致度**，不是独立人工真值；把它当评测入口时要另找人类标签。上表的命令与限制来自各自仓库；API 的新变化另见 [2026-10-15 定向更新](../research/2026-10-15/README.md)。

## 阅读与研究

阅读与研究类玩法都把"一段材料"变成"下一步读什么、信到什么程度"的判断，出口里始终保留"需要补充来源/材料"。

### reading-repro-layers
**复现报告先核哪一层证据**

- 输入：一份第三方复现报告摘要 + 它引用的原始评测仓库链接，以及你关心的一个具体结论。
- 判断问题：在有限动作里，下一步最该核对哪一层证据？
- 选项：`核对输入构造与案例来源` · `核对阈值与开发/测试切分代码` · `核对成本口径与样本单位` · `需要补充原始链接或版本` · `unknown`
- 借用机制：该仓库把成对输出、输入构造、顺序干预与成本分开记录，并用 `paper/analysis.py` 从已发布的原始输出复算，不需要 API。复算只覆盖其中一层（1,000 案例），所以先定位问题出在哪一层，而不是整份重算。（[David-DL-Space/sys1-eval](https://github.com/David-DL-Space/sys1-eval)）
- 第一次试：用报告里的一个具体数字，在仓库中定位 `paper/analysis.py` 或对应汇总文件，只核对那一步。
- 常见失败 / 何时交还人：报告未给出原始链接、版本或案例时无法定位层级，应先补信息；库里写的是 Laya 0.3.21 与 Jev 1.13 的历史实验，不能当作本轮新模型实测。

### reading-paper-next-section
**论文下一步读哪一节**

- 输入：一篇论文的标题、摘要与已有的若干片段（可含方法、结果、局限），以及你当前要回答的问题。
- 判断问题：下一步最该读文档的哪一部分？
- 选项：`背景与动机` · `方法与数据` · `结果与证据` · `局限与反例` · `读全文` · `现有材料不足` · `unknown`
- 借用机制：Laya 先用 router 选 checkpoint，再以 typed choice 在各命名问题上给出选项分布（多语言默认 1024，可显式 max_len 8192 并让 model 为 multilingual）。同一“读哪一节”的问题在题型与候选数之间分布会不同，分桶 abstention 正适合这种选择。（[NandhaKishorM/laya](https://github.com/NandhaKishorM/laya)）
- 第一次试：选一篇你读过的论文，把标题、摘要与结论各取一段作为输入，先看它是否建议你去读“局限”那一节。
- 常见失败 / 何时交还人：摘要里没写的东西不能假装读过；输入被截断或语言不同会改变分布，材料不足时应选“现有材料不足”并交还人。

### reading-passage-relevance
**段落是否算可用证据**

- 输入：一个查询意图 + 一段候选段落（可含标题、表格或代码）。
- 判断问题：这段材料相对当前问题属于哪一类证据强度？
- 选项：`直接支持` · `部分相关需其它证据` · `仅是背景` · `无关` · `需要补充上下文` · `unknown`
- 借用机制：原厂示例演示 RAG passage 分类；相关 cookbook 同时说明该分类器不构成独立安全边界，因此它只做候选筛选，不下最终结论。（[typesafe-ai/typesafe-public-examples](https://github.com/typesafe-ai/typesafe-public-examples)）
- 第一次试：拿 3 至 5 段真实检索结果，先人工标“支持/部分/无关”，再看判断是否与人工标签一致。
- 常见失败 / 何时交还人：相关不等于正确：段落相关不代表结论成立，同义改写也常被误判为无关；一旦用于权限或合规判定必须交还人。

## 开发与 agent

这一组把判断嵌进真实的工程动作里：读变更、处理工具输出、决定一步操作放不放行。

### dev-change-next-action
**文档变更的下一步核对动作**

- 输入：一段发布说明或变更文本 + 一句主张 + 可选的来源链接（本仓库 next-action 用例已含中英与混写）。
- 判断问题：下一步应采取的阅读/核对动作是什么？
- 选项：`inspect_source 核对原文` · `compare_contract 对照接口契约` · `read_in_context 结合实际调用` · `needs_more_context 先补上下文` · `unknown`
- 借用机制：本仓库已实现的 next-action 任务：固定动作契约、保留原生概率与 confidence、建议永不自动执行；unknown 是普通第五选项，与 needs_more_context、refusal、错误分别记录。（[Decisions Lab next-action](https://github.com/IndelibleVivi/decisions-lab)）
- 第一次试：运行离线 validate 与 demo，先观察一个故意判错和一个显式 unknown 的结果，再换成自己的变更文本。
- 常见失败 / 何时交还人：缺来源或缺当前依赖时不能硬判，应输出 needs_more_context；模型建议不自动变成操作，真实执行仍需人确认。

### dev-tool-output-triage
**工具输出太长怎么处理**

- 输入：一次工具调用的长返回值 + 当前 prompt 需要解决的问题。
- 判断问题：对这段工具输出应采取的上下文处理动作？
- 选项：`完整保留` · `摘要并保留原文与回取路径` · `隐藏但可恢复` · `需要人工决定` · `unknown`
- 借用机制：该 hook 拦截工具结果，由 sidecar 过滤大输出并保留 error/uncertain 块；confidence-no 块可隐藏但保留本地原文 recall，sidecar 不可达时原样透传。项目 demo 用 --fake 生成合成数据，去掉 --fake 会发真实 provider 调用，并要求 Claude Code 2.1.260+ 的 function hooks。（[GhalebDweikat/winnow](https://github.com/GhalebDweikat/winnow)）
- 第一次试：选 5 条历史工具输出，先用该项目的 --fake 合成 demo 走一遍，再对照“原始输出是否包含关键证据”。
- 常见失败 / 何时交还人：fail-open 只适合保障上下文可用，不能当作安全授权；hook 依赖客户端版本，漏删关键内容的错误要在小样本上单独审计。

### dev-agent-step-gate
**agent 的一步操作放不放行**

- 输入：agent 的一步计划 + 它要触碰的资源与参数。
- 判断问题：这一步应如何处理？
- 选项：`自动放行` · `自动阻止` · `转人工复核` · `需要补充上下文` · `unknown`
- 借用机制：该评测在 1% miss 目标下为 allow 与 block 分别选阈值并分区报告；结果显示某策略几乎不自动阻止，说明两级复核要先验证错误是否互补。（[yxsec/system-one-security-eval](https://github.com/yxsec/system-one-security-eval)）
- 第一次试：拿 20 条历史操作，先人工标“该放/该堵/该问人”，再看自动阈值在各动作分母下的错误。
- 常见失败 / 何时交还人：单一阈值和单一指标会掩盖类别不均衡；“再叫一个更强模型复核”不等于能纠正第一级错误，高代价分支要交还人。

## 知识整理

知识整理类玩法关心"把材料变成有结构的标签"，共同要求保留"无适用标签"出口，避免强行归类。

### know-narrative-code
**给一段叙述按编码表打码**

- 输入：一段自由文本叙述 + 一份很小的概念编码表（每个代码一句定义）。
- 判断问题：这段叙述最符合哪一个编码？
- 选项：`代码 A` · `代码 B` · `代码 C` · `都不适用` · `需要补充上下文` · `unknown`
- 借用机制：该实践对叙述做抽样加权的规模化编码，并把分阶段成本与样本单位分开记录；编码问题的 schema 开销与外推口径必须显式保留。（[pozapas/jev-calibrated-narrative-coding](https://github.com/pozapas/jev-calibrated-narrative-coding)）
- 第一次试：先在一小批已编码样本上试 20 条，核对每个代码的定义边界，再决定是否扩样。
- 常见失败 / 何时交还人：编码表边界含糊时模型会折中，需要先补定义；带法律医疗含义的字段不能用作专业结论，必须交还人。

### know-multilabel-extract
**从文本抽多个标签**

- 输入：一段文本 + 一份带定义的标签集合（可含“其它/无”）。
- 判断问题：这段文本应打哪些标签（可多选）？
- 选项：`标签一` · `标签二` · `标签三` · `无适用标签` · `需要补充定义` · `unknown`
- 借用机制：该库用 schema 驱动分类，区分单标签与阈值多标签；多标签有自己的阈值与基数评估，不能当成强制 K 选一的 softmax。（[fastino-ai/GLiNER2](https://github.com/fastino-ai/GLiNER2)）
- 第一次试：用 30 条已标注文本，先用单标签跑一遍，再加阈值多标签，比较漏标与错标的分布。
- 常见失败 / 何时交还人：标签定义重叠或阈值未定时会漂移；不要把所有同类架构当成同一条推理路径，跨模型要重新核验。

### know-fanout-questions
**一份材料拆成多个独立问题**

- 输入：一份材料 + 3 至 5 个彼此独立、各自有固定选项的问题。
- 判断问题：对每个子问题各选一个答案，并标记哪些“不适用”。
- 选项：`子问题各自取固定选项` · `需要补充材料` · `该子问题不适用` · `unknown`
- 借用机制：原厂示例的 fan-out 实践是并行提出多个问题、由代码判断适用性；打包多问不应被假定为“共享前缀免费”。（[typesafe-ai/typesafe-public-examples](https://github.com/typesafe-ai/typesafe-public-examples)）
- 第一次试：挑一份真实材料，写 3 个独立问题，先离线检查每个问题及选项，再在授权调用中记录分布与 usage，比较独立请求与打包请求。
- 常见失败 / 何时交还人：多问混在一起会互相影响，也可能重复计费；适用性必须由代码判断，不能把“多问都返回了”当成“都适用”。

## 创作与互动

这一组是合成内容方向：游戏、NPC、剧情导演、素材分流，以及音景切换。它们同样是"有限选项 + 交还人"的用法，只是候选更像创作，而不是分类标签。

### play-npc-reaction
**NPC 面对玩家一句话怎么反应**

- 输入：NPC 人设 + 玩家最近一句台词 + 极短的当前场景。
- 判断问题：NPC 的下一句反应属于哪一种？
- 选项：`友好配合` · `警觉试探` · `直接拒绝` · `沉默或回避` · `需要更多设定` · `unknown`
- 借用机制：该示例把每个候选单独当 yes/no 打分再归一化取 argmax，并支持选项轮换与并列等价解；逐候选归一与单次 K 选一的 softmax 含义不同。（[Yinsongxu/LLM2Jev](https://github.com/Yinsongxu/LLM2Jev)）
- 第一次试：写 10 组玩家台词，先固定 NPC 人设，看同一句话在不同人设下的反应是否合理，再调整候选。
- 常见失败 / 何时交还人：候选太少会逼出无意义选择，太多会稀释概率；标量反应不能替代剧情质量判断，最终剧本由人定。

### play-story-branch
**剧情导演选下一幕**

- 输入：当前剧情梗概 + 3 个候选分支（各一句）。
- 判断问题：下一幕应走哪个分支？
- 选项：`分支 A` · `分支 B` · `分支 C` · `需要更多设定` · `unknown`
- 借用机制：参考实现把状态/问题/选项序列化成一条指令，用 next-token 字母分类读候选（示例固定 temperature 0、max_tokens 8、top-5 logprobs）；不同 primitive 的覆盖率要另测。（[togethercomputer/tev1](https://github.com/togethercomputer/tev1)）
- 第一次试：用一个短梗概跑 3 个候选，检查是否总停在同一个分支，再改变选项顺序观察是否漂移。
- 常见失败 / 何时交还人：只取 top-5 logprobs 不能代表完整分布；候选少于 2 个或超过 24 个时参考实现会拒绝，剧本的最终取舍由人负责。

### play-asset-triage
**素材分流，要不要真的看媒体**

- 输入：素材清单（类型/大小/来源）+ 每个素材要解决的文本任务。
- 判断问题：这个素材该走哪条处理路径？
- 选项：`文本描述即可` · `必须查看图像` · `必须试听音频` · `需要人工浏览` · `unknown`
- 借用机制：该项目用单位置候选 token softmax 读分布，并提供 parity 脚本比对参考实现；README 记录某版本 vLLM 接受但忽略媒体，说明接受输入不等于读到图像。（[tic-top/llm2jev](https://github.com/tic-top/llm2jev)）
- 第一次试：选 5 张图/3 段音频，先只给文本描述跑一遍，再给真实媒体跑一遍，比较结论是否不同。
- 常见失败 / 何时交还人：后端可能静默忽略媒体，结论会假装“看过”；只用已获授权的素材，确认实际进入模型的输入。

### play-soundscape-switch
**互动音乐/环境场景切换**

- 输入：当前场景标签（如“雨夜/室内/紧张”）+ 用户显式偏好（如“再安静一点”）+ 一份既有音景 ID 列表。
- 判断问题：现在该切换到哪一段音景，还是保持或暂停？
- 选项：`音景 A` · `音景 B` · `保持当前` · `暂停` · `需要补充偏好` · `unknown`
- 借用机制：借用 typed choice（命名问题 + 有限选项 + 原生概率）从既有音景 ID 列表里选一个；Laya 的 router 可让中英场景标签走不同 checkpoint，但我们只把它当有限选择器。（[NandhaKishorM/laya](https://github.com/NandhaKishorM/laya)）
- 第一次试：用 5 个场景标签试一次，先确认返回的永远是列表里的 ID，再接播放器。
- 常见失败 / 何时交还人：它只在既有列表里选，不生成音乐、不把“紧张”当情绪诊断；没有合适音景时应给“暂停”或“需要补充偏好”，素材版权与最终播放由人负责。

## 生活与选择

没有专业背书也能用的两种日常玩法：候选筛选和优先级排序。两者都必须允许"都不合适/先放一放"。

### life-shopping-shortlist
**购物候选筛选**

- 输入：需求与硬约束 + 3 至 6 个候选（名称、关键参数、价格）。
- 判断问题：在给定约束下，哪个候选最合适？
- 选项：`候选一` · `候选二` · `候选三` · `都不合适` · `需要补充需求` · `unknown`
- 借用机制：该实现用 explicit null 表示“不支持/都不合适”，取代顺序敏感的 yes/no 候选，并把 state 缓存按问题展开且不共享别名；筛选要先给“都不合适”留出口。（[ozlabsai/typical](https://github.com/ozlabsai/typical)）
- 第一次试：把硬约束写进选项描述，先用 3 个候选试一次，看“都不合适”是否会被真实触发。
- 常见失败 / 何时交还人：参数没给全时模型会脑补卖点；价格与库存随时变，购买前要自己复核，超出建议范围的财务决定交还人。

### life-plan-order
**今天先做哪件事**

- 输入：待办清单（各含截止时间、依赖、耗时估计）+ 今天的可用时间。
- 判断问题：今天先推进哪一项？
- 选项：`任务一` · `任务二` · `任务三` · `都先放一放` · `需要补充时间或依赖` · `unknown`
- 借用机制：该实现用并行后缀打分与候选投影，并提供 Independent/CachedSerial/Parallel 三种模式核对结果是否一致；候选顺序不该改变结论。（[bespokelabsai/nimble](https://github.com/bespokelabsai/nimble)）
- 第一次试：用 6 条待办试一次，把清单顺序打乱再跑一次，看结论是否稳定。
- 常见失败 / 何时交还人：依赖与时间没写清时会给出漂亮但无法执行的排序；遗漏依赖时先补齐，再重新排序。

## 可靠性实验

这一组不是"用模型做判断"，而是"检验判断本身稳不稳"。它们把校准、顺序不变性、路径一致性和覆盖检查当成可玩的实验。

### rel-choice-order-invariance
**选项顺序会不会改变结论**

- 输入：一个判定问题 + 同一组选项的两个顺序版本。
- 判断问题：两个顺序版本是否给出同一个结论？
- 选项：`一致` · `结论漂移` · `概率变但结论不变` · `无法判断，需补样本` · `unknown`
- 借用机制：该项目用“翻转标签后概率不变”的 parity 测试检验 Noul 不变性；同时 kev README 承认同一问题内部选项顺序仍可能影响结果，所以不变性必须逐任务验证。（[ozlabsai/typical](https://github.com/ozlabsai/typical)）
- 第一次试：取 10 个真实问题，各生成两个顺序版本，记录是否换答案、概率差多少。
- 常见失败 / 何时交还人：只测一个例子就下结论不可靠；顺序敏感性与上下文截断容易混淆，需要固定内容后再比。

### rel-local-hosted-parity
**本地和托管是不是同一个结果**

- 输入：同一批输入，两条运行路径（如本地推理与兼容服务）的输出。
- 判断问题：两条路径在同一输入上是否数值一致？
- 选项：`logprob/概率在容差内一致` · `argmax 一致但数值不同` · `结论不同` · `需要补更多样本` · `unknown`
- 借用机制：该项目的 parity.py 对比渲染后的精确 prompt 与 Transformer 参考的 logprob gap、probability gap 和 argmax，覆盖 image/video/audio 探针，不一致就非零退出。（[tic-top/llm2jev](https://github.com/tic-top/llm2jev)）
- 第一次试：选 5 条输入，用两条路径各跑一遍，先比 argmax 再比概率差，记录差异最大的那条。
- 常见失败 / 何时交还人：后端版本差异会让同一模型表现不同；“跑通”和“数值一致”是两回事，质量还要另测，不能凭一次一致就宣称可替换。

### rel-protocol-projections
**同一个分布，两种 confidence**

- 输入：一次判断的完整分布 + 目标协议要求的 confidence 字段定义。
- 判断问题：这个 confidence 字段属于哪种统计口径？
- 选项：`归一化 top 概率` · `归一化熵` · `期望 index（Score）` · `无法从分布确定` · `unknown`
- 借用机制：该运行时对同一分布给出两种命名的 confidence 投影（TypeSafe 归一化 top 概率 =(K*pmax-1)/(K-1)，Laya 归一化熵 =1-H/logK），协议换算会改变 confidence 而底层概率不变。（[ollaya-dev/ollaya](https://github.com/ollaya-dev/ollaya)）
- 第一次试：拿一次真实分布，分别按两种公式算一遍，看数值是否相同、是否被当成同一个“可信度”。
- 常见失败 / 何时交还人：把两个口径当成同一个数会误读为模型变强或变弱；换运行时、换协议都要重新核对字段语义，不能靠公式猜。

### rel-abstention-buckets
**按分桶决定哪些送人复核**

- 输入：一批判断结果（每次的完整分布与 confidence）+ 已标注的一小批结果。
- 判断问题：这批结果该按什么规则送人复核？
- 选项：`按题型分桶设阈值` · `按候选数分桶设阈值` · `全局单一阈值` · `全部送人复核` · `需要补充标注` · `unknown`
- 借用机制：该实现用 router 选 checkpoint，再以 typed choice 在各命名问题上给出分布，并按题型与候选数做 abstention 分桶。当前 README 记录 laya-ts 0.4.7 修正了 act_probability 的 double softmax、恢复 option_order 并新增大量选项的 tournament。（[NandhaKishorM/laya](https://github.com/NandhaKishorM/laya)）
- 第一次试：拿 50 条已标注结果，先看全局阈值漏掉多少，再按题型/候选数分桶重算覆盖率。
- 常见失败 / 何时交还人：全局单一阈值会按任务规模失配；多语言默认只喂 1024、要 8192 得显式开启；分桶键不可达或样本太小时门槛不可用，高风险判定宁可多送人。

### rel-replay-threshold-coverage
**离线回放与阈值覆盖检查**

- 输入：一份本仓库的记录目录（record.json）+ 对应用例文件。
- 判断问题：在给定阈值下，多少条判断真正可用、其中多少条正确？
- 选项：`只统计正常作答` · `把 unknown/refusal 也算可用` · `把错误也算可用` · `先补记录再评估` · `unknown`
- 借用机制：本仓库 replay 校验记录完整性（拒绝篡改与漂移），阈值覆盖只用已记录的 maxP 统计，unknown/refusal/error 不计入可采用动作，也不使用统一置信度。（[Decisions Lab next-action](https://github.com/IndelibleVivi/decisions-lab)）
- 第一次试：先跑 demo 生成合成记录，再用 --threshold 0.6 回放，观察覆盖与正确率如何随阈值变化。
- 常见失败 / 何时交还人：把 unknown 或错误当可用会虚高覆盖；阈值只该在显式选择时使用，缺记录时不能悄悄把子集当完整评估。

## 完整合成示例

下面 6 个短示例都是**原创合成输入**，可以照着改成自己的任务。输出形态指推荐的返回结构，不代表某个模型的实际返回。

### 示例 1 · 变更核对（`dev-change-next-action`）

```text
输入：
  变更：发布说明 v2.1 新增字段 retry_after_ms，默认 0 表示不重试；该字段替代旧的 retry_ms，
        旧的 retry_ms 将在 v3 移除。
  主张：这次只是文档措辞调整，不影响调用方接口。
  来源：https://example.invalid/releases/v2.1
问题：下一步应采取的阅读/核对动作是什么？
选项：inspect_source / compare_contract / read_in_context / needs_more_context / unknown
期望输出形态：{ "choice": "compare_contract", "probabilities": { 五个选项各一个概率 } }
怎么用：把 choice 作为建议展示，附上原文位置；人不采纳时记录改选理由。
```

### 示例 2 · 论文下一节（`reading-paper-next-section`）

```text
输入：
  标题与摘要：一篇关于"用小型决策模型做文献筛选"的论文摘要。
  已有片段：结果表里 micro-F1 从 0.499 提到 0.748，未说明阈值怎么选的。
  当前问题：这个提升可信吗？
问题：下一步最该读文档的哪一部分？
选项：背景与动机 / 方法与数据 / 结果与证据 / 局限与反例 / 读全文 / 现有材料不足 / unknown
期望输出形态：{ "choice": "方法与数据" }（去核对阈值选择与切分）
怎么用：把它当阅读路线建议；若摘要与片段不足以判断，选"现有材料不足"去取原文。
```

### 示例 3 · 购物候选（`life-shopping-shortlist`）

```text
输入：
  约束：预算 ≤ 800 元、必须可折叠、三天内到货。
  候选：A 折叠椅 699 元（5 天到货）；B 折叠凳 480 元（现货）；C 折叠椅 820 元（现货）。
问题：在给定约束下，哪个候选最合适？
选项：候选一 / 候选二 / 候选三 / 都不合适 / 需要补充需求 / unknown
期望输出形态：{ "choice": "候选二" }（A、C 各有硬约束不满足）
怎么用：把"都不合适"当作合法结果展示；价格与库存由使用者下单前自行复核。
```

### 示例 4 · NPC 反应（`play-npc-reaction`）

```text
输入：
  人设：守夜的老门房，嘴硬但心软。
  玩家台词：这么晚了还拦我，信不信我明天投诉你？
  场景：雨夜，城堡侧门。
问题：NPC 的下一句反应属于哪一种？
选项：友好配合 / 警觉试探 / 直接拒绝 / 沉默或回避 / 需要更多设定 / unknown
期望输出形态：{ "choice": "警觉试探" }
怎么用：把反应方向交给编剧扩写成台词；反应标签不能替代剧情质量判断。
```

### 示例 5 · 音景切换（`play-soundscape-switch`）

```text
输入：
  场景标签：雨夜 / 室内 / 紧张
  用户偏好：再安静一点
  音景列表：rain-window（窗边雨声）/ low-drone（低频悬念）
问题：现在该切换到哪一段音景，还是保持或暂停？
选项：rain-window / low-drone / keep / pause / needs_preference / unknown
期望输出形态：{ "choice": "rain-window" }（把通用配方的音景 A/B 换成实际 ID）
怎么用：没有合适音景时选"暂停"或"需要补充偏好"；它不生成音乐，也不做情绪诊断。
```

### 示例 6 · 路径一致性（`rel-local-hosted-parity`）

```text
输入：
  5 条同一问题，分别用本地推理与兼容服务跑一遍，记录两条路线的 argmax 与概率。
问题：两条路径在同一输入上是否数值一致？
选项：logprob/概率在容差内一致 / argmax 一致但数值不同 / 结论不同 / 需要补更多样本 / unknown
期望输出形态：{ "choice": "argmax 一致但数值不同", "notes": "第 3 条概率差最大" }
怎么用：把差异最大的样本挑出来单独复核；"跑通"不等于"数值一致"，更不能直接宣称可替换。
```

## 离线命令

只有 next-action 实验在本仓库有真实实现，下面命令可离线运行、不联网、不调用模型。其它玩法需要调用方自己实现判断逻辑，本仓库不提供对应 CLI；「现成项目怎么开始」列的是各项目自己的入口。

```bash
# 校验用例 schema、id 唯一与来源组切分（不写文件）
python3 -m decision_lab validate experiments/next-action/cases.json

# 确定性规则 baseline -> 写入一次合成运行记录
python3 -m decision_lab baseline-run experiments/next-action/cases.json \
    --run-dir runs/next-action/baseline-001

# 离线合成演示：含一个故意判错与一个显式 unknown
python3 -m decision_lab demo --run-dir runs/next-action/demo-001

# 从已记录响应离线回放；--threshold 只使用已记录的 maxP 统计量
python3 -m decision_lab replay runs/next-action/demo-001 --threshold 0.6

# 生成两条原生路线的请求体，检查形状但不发送
python3 -m decision_lab prepare experiments/next-action/cases.json --route jev --limit 1
python3 -m decision_lab prepare experiments/next-action/cases.json --route decisions --limit 1
```

以上命令在 2026-10-15 于本机以临时运行目录（替代 `runs/`）实际执行通过：`validate` 报告 `OK: 25 cases (dev=14, test=11), 13 source groups`；`demo` 写入合成记录并给出 `accuracy=0.875 (21/24)`；`replay --threshold 0.6` 给出 `covered 24/25`；`baseline-run` 写入合成记录。它们是**合成/基线**结果，不是模型实测，也不构成质量或价格声明。运行时把 `--run-dir` 换成本地新目录，即可保留自己的记录。

## 来源核查记录

本页的玩法机制来自两类来源：**2026-10-08 调查快照**（`research/2026-10-08/`，完整的问题、实现路径与仓库机制调查）与**2026-10-15 定向复核**（对下面部分项目的当前 README / 说明做有界重读）。两个日期都写在配方的 `source_date` 里。

| 项目 URL | 最近核查日期 | 核查范围 |
| --- | --- | --- |
| https://github.com/GhalebDweikat/winnow | 2026-10-15 | README 重读：保留/隐藏块、原文 recall、demo `--fake` 与 function hooks 要求 |
| https://github.com/NandhaKishorM/laya | 2026-10-15 | README 与 `examples/README.md` 重读：0.4.7 变更、multilingual 限制、41 例 8 阶段路径 |
| https://github.com/typesafe-ai/WorkflowEvals | 2026-10-15 | README 重读：`uv sync --locked`、四个 workflow、`--dry-run`、参考一致度口径 |
| https://github.com/David-DL-Space/sys1-eval | 2026-10-15 | README 重读：`paper/analysis.py` 从已发布原始输出复算，不需 API |
| https://github.com/typesafe-ai/typesafe-public-examples | 2026-10-08 | 根 README 已看；RAG cookbook 子页本轮未取到，相关配方继续用快照 |
| https://github.com/AppliedMachineLearning-Lab/jev-benchmarking | 2026-10-08 | 相关源码 / 汇总（冻结模板、阈值与测试集） |
| https://github.com/yxsec/system-one-security-eval | 2026-10-08 | 阈值代码 / 汇总 / 审计说明 |
| https://github.com/pozapas/jev-calibrated-narrative-coding | 2026-10-08 | 指标 / 成本代码 / 汇总 |
| https://github.com/fastino-ai/GLiNER2 | 2026-10-08 | AutoExtractor / 具体实现已读 |
| https://github.com/Yinsongxu/LLM2Jev | 2026-10-08 | 原作者示例代码已读 |
| https://github.com/togethercomputer/tev1 | 2026-10-08 | decide.py / 模型卡；权重许可待定 |
| https://github.com/tic-top/llm2jev | 2026-10-08 | 后端代码 / parity 脚本已读 |
| https://github.com/ozlabsai/typical | 2026-10-08 | parity 测试定义 / release notes |
| https://github.com/bespokelabsai/nimble | 2026-10-08 | 源码 / 测试定义 |
| https://github.com/ollaya-dev/ollaya | 2026-10-08 | Rust 回答层已读 |

**本轮重查的边界。** 2026-10-15 只重读了 winnow、laya、WorkflowEvals、sys1-eval 的 README 与 typesafe-public-examples 的根 README；这是文档与仓库说明层面的复核，**没有安装或运行这些项目，也没有新增模型实测**。typesafe-public-examples 的 RAG cookbook 子页本轮没有取到，涉及 RAG passage 的配方仍标 2026-10-08；未重查的项目继续沿用 2026-10-08。`browser-use/jev-ultrafast`、`Mapika Decider`、`githubnext/localjev` 等条目仍在快照 watchlist 中、未经源码审计，因此没有进入玩法列表——仅凭仓库名或 runtime 里出现的 adapter 名称不足以断言其功能。

**原生契约更新另成一页。** [2026-10-15 定向更新](../research/2026-10-15/README.md)记录本轮对 OpenAI Decisions、TypeSafe Jev 以及 Fastino / Cloudflare / Upstage 的文档与 SDK 增量核对，并给出两份可复制的 `curl` 示例（TypeSafe 与 OpenAI 各一份）。阅读站首页的“复制任务 JSON”复制的是本项目的**通用任务 JSON**（输入／问题／选项），不是任何一家的原生请求体；要发真实请求，请按那一页的示例自行配置凭据，并确认调用与费用。本页不据此断言任何模型的质量、价格或可用性。

## 边界与不适用

- 这本册子是"可以怎么用"的样例集合，不是穷尽的玩法市场，也不是模型能力的完整清单。
- 玩法中的场景（NPC、剧情导演、购物筛选、素材分流、音景切换等）是本项目提案；可复用的是所引项目的机制，不是"那个项目已经支持这个玩法"。
- 数量与比例会随新的具体用例改变；`catalog/recipes.json` 是配方事实真源，本页是它的展开说明。
- 模型的建议需通过调用方校验；采用某个建议不等于授予额外的执行权限。
- 记录里不写私人信息或账户路径；使用真实输入时，记录应按输入敏感程度保管。
