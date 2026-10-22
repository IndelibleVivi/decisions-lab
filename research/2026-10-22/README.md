# 2026-10-22 · Decisions API 能力与实验

这一轮沿原生接口的能力追问题：有限选项能产生什么计算对象，返回分布能做哪些运算，图片能否直接定义判断标准。新增 [能力研究方法](../../docs/api-capabilities.md)、[三组离线实验](../../experiments/api-capabilities/README.md)与[可查询索引](../../catalog/capabilities.json)。后四条研究设计保留各自对照和实现缺口。

**核查日期：2026-10-22。** [updates.json](updates.json)记录 15 项第一方文档／源码／作者材料和一篇论文，共 16 项来源、8 条变化；[12 项 probes 的当前版本](public_probe_protocol.json)保留原始 fixture，并更新接口前提。这里只做定向核查，不重写 [10-08 快照](../2026-10-08/README.md)、[10-15 增量](../2026-10-15/README.md)或 [10-20 Clairic 调查](../2026-10-20/README.md)。未访问凭据、未请求模型，provider 状态仍为 `NOT_RUN`。

## 核查到的变化

| 能力依据 | 本轮核查 | 对实验的影响 |
| --- | --- | --- |
| OpenAI 多问题 | 直接打开 reference 为 1–400 题；固定 SDK revision 的 docstring 仍写 1–200 | 请求数、问题数和服务端边界分别记录 |
| 原生输入、缓存与拒答 | reference 包含消息、图片及 tool call/output；SDK 顶层已有 cache 字段；单题可拒答 | 不把原生 HTTP、SDK 表达能力和实际接受范围混为一谈 |
| Jev 图片标准 | 图片可通过顶层 assets 引用进入 criteria，需实验 header | 现场交换 K1/K2/K3 的定义，检测关系判断与视觉捷径 |
| Jev 多题语义 | 官方声明独立并行；64k 每请求／32k 每题，长 context 另需开关 | 单问、打包和重复波动一起比较，保留每种预算 |
| Clairic | list、forecast、分 pass 与远期预测限制有具体声明 | 列表状态、单位变换、网格效应形成独立题本 |
| Live 与 Clef-Omni | Live 结果按源事件关联且可能乱序；Omni 有 joint head 与媒体占用 context | 前缀标签、事件处理和跨模态时序分别实验 |

## OpenAI reference 与 SDK 仍不一致

本轮直接页面写 400 题；搜索缓存的同一页面仍曾返回 200，因此不以搜索摘要定当前值。固定 `openai-python` revision `d40a5e1283e6d91ed4bebac6e569b27d5fe02c52` 的请求类型说明仍写 200，并只描述文本／图片输入，不含工具项。它已有 `prompt_cache_key` 和 `prompt_cache_options`。这些是文档和源文件观察，未验证 SDK runtime 或服务端是否拒绝第 201 题。[reference](https://developers.openai.com/api/reference/resources/decisions/methods/create/) · [固定 SDK 源文件](https://github.com/openai/openai-python/blob/d40a5e1283e6d91ed4bebac6e569b27d5fe02c52/src/openai/types/decision_create_params.py)

Choice 的文档上限仍为 255。两个布尔变量的 16 个函数可以整体作为候选；三个变量的 256 个函数无法放进同一个这样的 Choice。这个边界能用离线枚举确认，是否能通过分解保持语义仍需模型实验。

## 研究如何进入工具

[api-lab 实验入口](../../experiments/api-capabilities/README.md)负责多问题原生请求、原始响应导入、分题归一化和离线评分。三组题本是 rule-compile、probability、visual-criteria。前两组可比较 OpenAI/Jev；图片作为 criteria 的实验使用 Jev 的原生资产契约，不偷换成另一种图像输入任务。

规则真值由穷举产生，概率真值来自已知世界，图像真值来自坐标关系。合成 demo 有意包含错误与失败；报告必须显示 coverage 和反例，不能把未返回的题算作概率 0。实际命令、题本数量与导入格式以实验说明和 CLI 输出为准。

旧 [12 probes](../2026-10-08/public_probe_protocol.json)从未执行，本轮没有将它们标为已跑。新日期版本修正图片支持、context 和多问题前提，同时保留原 source ID 的日期来源。三组新题本覆盖其中部分机制，不等于旧 12 项协议全实现。

## 继续研究的四个方向

- **语义特征库**：直接判断、人工问题库、一次提议、迭代提议、embedding 对照；问题数量和特征分布编码分开。官方参考结果使用历史 Jev 1.12。[第一方 cookbook](https://docs.typesafe.ai/cookbooks/autoresearch_feature_discovery)
- **语义寻址**：同一批段落在平铺、逐段、多层与多路径下的召回；树结构与计算量分开。路径几何平均首先是搜索分数。[行寻址](https://docs.typesafe.ai/cookbooks/semantic_find) · [层级搜索](https://docs.typesafe.ai/cookbooks/hierarchical_classification)
- **Clairic 表示变换**：有效实体列表、正比例单位变换、预测 horizon、网格与留出误差。[官方字段和局限](https://developers.cloudflare.com/changelog/post/2026-10-19-clairic-workers-ai/)
- **时间与多模态**：前缀修正和迟到结果；音视频的相对次序、缺失模态与事件持续时间。[Live](https://developers.openai.com/api/docs/guides/decisions-voice) · [Omni](https://developers.cloudflare.com/workers-ai/models/clef-omni/)

完整题本设计与实现状态见[能力方法章](../../docs/api-capabilities.md)。这些研究设计没有被写成已实现或已采集结果。

## 来源与限制

完整来源 ID、URL、日期和证据类型在 [updates.json](updates.json)，能力条目按 source ID 关联。不重新核价，不刷新全量供应商普查，不执行上游 cookbook、训练或模型。Jev 图像处于实验状态；Clairic 非空 list/forecast 等仍超出现有 typed-values 题本处理范围。模型卡不证明托管实现与自托管实现逐项相同。

真实响应缺失时，能得出的结论仅限于数学参照、生成器、请求形状与评分流程。质量、校准、实际延迟和费用仍等待有上限的独立采集。
