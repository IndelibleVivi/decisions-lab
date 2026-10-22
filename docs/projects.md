# 相关项目地图

> 来源截点：2026-10-08。以下审读深度来自该期调查；未在本项目重新运行上游测试或模型。

从要解决的问题选择阅读入口。模型、SDK、运行时和评测仓库分别归类；兼容接口不保证语义、质量或许可相同。

新变化与新用法另见 [2026-10-22 定向增量](../research/2026-10-22/README.md) 和 [妙妙玩法配方册](playbook.md)。下面仍是 2026-10-08 的项目地图，不将旧审读自动标为新验证。

## 调用契约与 SDK

怎样发出一个判断请求，并保留真实返回语义？

| 项目 | 值得看什么 | 调查读到了哪里 |
| --- | --- | --- |
| [typesafe-ai/typesafe-sdk-python](https://github.com/typesafe-ai/typesafe-sdk-python) | 同步 / 异步、typed answers、重试、HTTP/2 | README / 原厂代码资料审读 |
| [typesafe-ai/typesafe-sdk-js](https://github.com/typesafe-ai/typesafe-sdk-js) | 由 questions 推断答案类型 | README / 类型接口资料审读 |
| [openai/openai-python](https://github.com/openai/openai-python) | Decisions 请求类型、refusal、响应类型 | 资源 / 类型文件；已记录 blob SHA |

## 开放模型与决策头

模型怎样把输入变成候选概率，哪些条件限制这种计算？

| 项目 | 值得看什么 | 调查读到了哪里 |
| --- | --- | --- |
| [NandhaKishorM/laya](https://github.com/NandhaKishorM/laya) | 校准、confidence、按题型 / 候选数分桶 abstention | 固定 revision 源码 / 测试定义已读 |
| [jaredpalmer/kev](https://github.com/jaredpalmer/kev) | pointer head、共享前缀、优化路径概率一致性 | 固定 revision 源码 / 测试定义已读 |
| [ozlabsai/typical](https://github.com/ozlabsai/typical) | state cache、factored null、Noul 不变性 | parity 测试定义 / release notes |
| [togethercomputer/tev1](https://github.com/togethercomputer/tev1) | next-token 字母分类、Chat Completions 参考实现 | decide.py / 模型卡；权重许可待定 |
| [bespokelabsai/nimble](https://github.com/bespokelabsai/nimble) | 候选投影、并行后缀、不污染缓存 | 源码 / 测试定义；demo 另列 |
| [fastino-ai/GLiNER2](https://github.com/fastino-ai/GLiNER2) | 模型架构分发、encoder、多标签分类 | AutoExtractor / 具体实现已读 |

**laya 的边界：** 默认窗口较短。支持多语言不意味着各语言准确率相同；决策头预算与长文本截断需要另测。

**kev 的边界：** 同一问题内部仍可能受选项顺序影响；微调在部分任务上退化，概率校准依赖输入分布。

**typical 的边界：** preview 与当前版本的结果不能混算；旧版存在位置和早期证据偏差，公开 JevBench 子集也不是封闭排行榜。

**tev1 的边界：** top-5 logprobs 不能当成完整的 255 选项分布；需保留 dev 集使用和权重许可的疑点。调查未执行上游测试。

**nimble 的边界：** 当前本地 checkpoint 的 8K/255 选项/T=1.0 与 demo 的 8K/26 选项/拟合温度不同；旧 benchmark 和温度不能直接迁移。

**GLiNER2 的边界：** 不能把全部 GLiNER 架构视作同一条推理路径，也不能推定其兼容 GLiDE；context 上限和 typed API 投影未完整核查。

## 本地 runtime 与兼容适配

怎样在自己的机器上运行，协议转换改变了什么？

| 项目 | 值得看什么 | 调查读到了哪里 |
| --- | --- | --- |
| [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp) | 原生 System One、Clef 图像、joint schema | 正式发行 / 当前文档 / merged PR |
| [ollaya-dev/ollaya](https://github.com/ollaya-dev/ollaya) | 权重谱系、ONNX / GGUF、协议投影 | Rust 回答层已读 |
| [Yinsongxu/LLM2Jev](https://github.com/Yinsongxu/LLM2Jev) | 逐候选 yes/no 后归一；视觉动作等价解评估 | 原作者示例代码已读 |
| [tic-top/llm2jev](https://github.com/tic-top/llm2jev) | 单位置候选 token softmax；backend / media parity | 后端代码 / parity 脚本已读 |
| [typesafe-ai/system-one-adapter-python](https://github.com/typesafe-ai/system-one-adapter-python) | 普通 LLM 接入问题契约；重试与原始输出 | 相关代码 / 说明已读 |

**ollaya 的边界：** 当前 README 与源码注释对 llama.cpp 支持的描述存在新旧差异。运行成功、导出数值一致和任务质量要分别测。

**LLM2Jev 的边界：** 逐候选 yes 概率重新归一化会改变含义，不能视作通用校准分类器；媒体与运行时一致性依赖具体版本。

**llm2jev 的边界：** 调查记录了特定 vLLM/SGLang 版本的媒体忽略、计分与短音频问题。支持的是具体模型和后端组合，不是所有组合。

## 工作流与使用实践

模型判断怎样进入工作流，失败后怎样找回原文？

| 项目 | 值得看什么 | 调查读到了哪里 |
| --- | --- | --- |
| [GhalebDweikat/winnow](https://github.com/GhalebDweikat/winnow) | shadow、回放、原文 recall、hook 失效处理 | hook / policy / 模型辅助标签来源已读 |
| [typesafe-ai/WorkflowEvals](https://github.com/typesafe-ai/WorkflowEvals) | 版本、恢复、参考模型、usage、缺价处理 | README / 工作流结构审读 |
| [typesafe-ai/typesafe-public-examples](https://github.com/typesafe-ai/typesafe-public-examples) | fan-out、RAG passage 示例 | 原厂归属 / 结构确认 |

**winnow 的边界：** hook 依赖客户端版本。过滤失败时保留原文适合保障上下文可用性，不能直接移植为安全授权的失败策略。

## 评测与领域研究

一个分数究竟测了什么，阈值与成本怎样复核？

| 项目 | 值得看什么 | 调查读到了哪里 |
| --- | --- | --- |
| [David-DL-Space/sys1-eval](https://github.com/David-DL-Space/sys1-eval) | 成对输出、输入构造、顺序干预、成本 | 源码 + 1,000 案例独立离线复算 |
| [AppliedMachineLearning-Lab/jev-benchmarking](https://github.com/AppliedMachineLearning-Lab/jev-benchmarking) | 冻结模板、hash cache、阈值 / 测试分开 | 相关源码 / 汇总已读 |
| [yxsec/system-one-security-eval](https://github.com/yxsec/system-one-security-eval) | allow / block 阈值、分区、错误互补性 | 阈值代码 / 汇总 / 审计说明 |
| [pozapas/jev-calibrated-narrative-coding](https://github.com/pozapas/jev-calibrated-narrative-coding) | 抽样加权、分阶段成本、总体外推 | 指标 / 成本代码 / 汇总已读 |

## 继续追踪的线索

以下线索尚未达到已核实体或代码审读的相同证据深度。保留线索，避免把列表中的名字当成已验证产品。

- **[SecJev](https://arxiv.org/abs/2610.03073)**：论文及 Kev 衍生方向的研究线索；原始 checkpoint、仓库与许可尚未追清。
- **[arXiv2610.00346 comparative decision-model sample](https://arxiv.org/abs/2610.00346)**：比较研究线索；论文采用的市场样本不等于完整供应商普查。
- **[Mapika Decider](https://github.com/Mapika/decider)**：已找到原作者 GitHub；本期未做源码审计，具体家族、runtime 与许可仍待核。
- **[JevK5, Winnow-E4B, Jeb/Jebadiah, Jeeves, Decima, Cygnet, Arbiter, Snap, Von](https://github.com/ollaya-dev/ollaya/blob/main/crates/ollaya-decision/src/lib.rs)**：运行时中出现了相应 adapter 名称；这不足以证明各模型的原厂身份、当前能力或许可，不能把 runtime 支持数当作原厂数量。
- **[githubnext/localjev](https://github.com/githubnext/localjev)**：由 xuhaodev 的模型卡链接到此；本期未审读源码。
- **[joyfox/Qwen3.5-0.8B-JEV](https://huggingface.co/joyfox/Qwen3.5-0.8B-JEV)**：模型卡发现项，涉及自定义 head/runtime；具体许可和契约尚未继续核查。
- **[xuhaodev/Qwen3-1.7B-Jev](https://huggingface.co/xuhaodev/Qwen3-1.7B-Jev)**：同一中文作者家族的线索；本期主要审读 4B 模型卡，不能直接移植 4B 的能力结论。
- **[browser-use/jev-ultrafast](https://github.com/browser-use/jev-ultrafast)**：Laya README 中的原作者链接；可作为使用实践或微调方向继续看，本期未审计。
- **[tycoding/jev-java-sdk](https://github.com/tycoding/jev-java-sdk)**：名称含 Jev，但 README 指向通过 receptron/laya-onnx 运行本地 Laya；尚未证明它是 TypeSafe HTTP client，未纳入十项深读。
- **[gliner-decide-metal](https://github.com/shantanugoel/gliner-decide-metal)**：Apple MLX runtime 线索；本期未审读代码。
- **[Bespoke Nimble commercial API](https://nimble.bespokelabs.ai/)**：官网文本提取失败，条款提及 Nimble API；目前仅确认原仓库 public demo，不推断商业价格或 SLA。
- **[Perplexity Decider v1.1 open weights](https://docs.perplexity.ai/docs/decisions/quickstart)**：已确认 v1.1 原生 API；其他来源提到的 v1 开放权重，不代表 v1.1 checkpoint 和许可相同。
- **[Solar Decide Flash direct Upstage contract](https://console.upstage.ai/docs/models/solar-decide)**：10 月 8 日确认了 OpenRouter 路线；原厂文档当时仅明确 solar-decide，Flash 直连接口待核。
- **[EmpirioLabs Decide1, Decide1Omni, Aplomb1Omni legacy pages](https://docs.empiriolabs.ai/models/aplomb-1)**：当前统一 Aplomb1 已核；搜索仍能找到旧页，不将旧名称自动计作不同的当前产品。
- **[CJ-Dataset](https://huggingface.co/datasets/bbldCVer-hf/CJ-Dataset)**：训练数据线索，不能计作模型供应商；混合、研究用途与非商用条款需要逐来源核查。
- **[zh-decision-bench](https://huggingface.co/datasets/CodyQin/zh-decision-bench)**：中文评测数据线索；本期未深入审读，也不是模型条目。
- **Chinese/regional vendors beyond Alibaba/Tencent**：调查没有形成穷尽性否定结论；确认 Alibaba/Tencent 不证明其他中国、日本或俄罗斯生态没有产品。

完整固定 revision、源码位置、机制、许可与局限见 [结构化项目记录](../research/2026-10-08/repositories.json)。
此页由 `python3 tools/catalog.py render` 从 catalog 的分组和日期快照生成；修订事实应进入有日期的新证据。
