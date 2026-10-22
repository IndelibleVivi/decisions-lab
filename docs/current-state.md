# 当前状态

更新时间：2026-10-23。

- **研究基础设施源码已升级**：[方法与命令](research-infrastructure.md)提供oracle构念控制、显式trial/replicate、planned/missing、只读legacy账本、api-lab/Clairic有界collector、四类分组生成器、配对比较与少簇限制。规则编译→穷举→最小反例→修复及版本探针已贯通离线synthetic/导入路径。collector保留原始bytes和失败耗时，resume跳过uncertain，显式重试承认潜在重复计费；token预算只约束输入估算。尚无真实provider采集、缓存收益、模型修复收益或生产结论。
- **API 能力依据已整理**：[10-22 定向核查](../research/2026-10-22/README.md)记录 16 项来源、8 条变化，核对 OpenAI reference／SDK 差异、Jev 原生图片标准和多题 context、Clairic 表示族、Live 与 Clef-Omni 条件。历史 census 与既有增量保留日期，不重新核价。
- **能力研究有明确入口**：[7 个能力方向](api-capabilities.md)与[可查询索引](../catalog/capabilities.json)连接来源、假设、对照、指标和本地覆盖。规则编译、概率组合、视觉 criteria 的离线 `api-lab` 已实现原生多题请求、导入、独立评分与快照 replay；其余四条保留研究设计，provider 均 NOT_RUN。新日期的 12 probes 是设计修订，不是执行结果。

- **研究可读**：首期日期快照、23 个实体、21 个项目、171 条来源索引与 6 项研究已整理；不是所有来源在本轮重新审查。
- **定向更新已整理**：[10-15 增量](../research/2026-10-15/README.md)记录 30 条来源、12 条变化，覆盖 Jev 1.14、OpenAI Decisions 文档／SDK 差异及 Cloudflare、Fastino、Upstage。历史快照保留，未重查全量目录。
- **Clairic 增量已整理**：[10-20 调查](../research/2026-10-20/README.md)记录 8 项官方来源、7 项变化；原始 schema 和官方示例固定 revision，四条 Cloudflare 路线的标价按本轮日期记录。旧增量可以用 catalog 的 `--date` 查询。
- **类型化输出离线工具已实现**：[方法章](typed-values.md)和[三组实验](../experiments/typed-values/README.md)包含缺失值、提取后计算及上下文损失、区间评估。7 个原创请求草案、编辑答案和干预定义位于 `examples.json`；provider 状态仍为 NOT_RUN，provider results 为空。独立的 `typed-values` 子命令可验证、准备请求、生成 synthetic baseline／demo、导入本地响应并重放评分；字段 null、来源关系、金额计算、三路径判断与区间指标分别报告。原生字段语义不变；Clairic有界collector已实现但未进行真实采集，题本loader可扩展现有实验的合法案例。
- **玩法可探索**：[20 种配方](playbook.md)按六组组织，每项给输入、选项、现成项目、第一步与失败方式；两项已有离线实验，其余是接入提案。项目来源各自标日期，原创玩法不冒充上游已有功能。
- **历史可复算**：随包 1,000 个案例、4,000 条概率记录的复算与基准结果一致，14 项作者汇总核对一致。原始输入不随项目分发。
- **离线实验已实现**：25 个原创合成 next-action 用例、确定性 baseline、含错误和 unknown 的 demo、记录与完整性校验 replay。
- **next-action API adapter 候选**：TypeSafe Jev 与 OpenAI Decisions 原生 contract；继续固定 `jev-1.13.0` / `gpt-6-luna` 的现有文本 Choice profile。增量文档不自动启用 Box、图像、cache 或新版模型。文档核对与 mock 测试不等于真实 API 可用，live 推理未运行。
- **阅读站源码已更新**：24 页从 Markdown/catalog 构建；本轮新增正文与资产 allowlist，更新入口由 catalog 驱动。首屏粒子作品和标题直接操控保留；下方由像素卡带、稀疏信号场、PLAY 招牌轮播和自托管字体构成。unknown 从编号动作中独立出来，ok／unknown／refusal／error 的文字、画面与结果读数同步；后两类为明确标注的离线示例，没有选中动作或实际请求，不产生概率与 confidence。分类、搜索、fragment、任务 JSON 复制、项目入口、概率示意、历史矩阵与三例练习均保留。下方共享暂停联动招牌、图标、信号场和实验动态；减少动态、后台、离屏停止，静态选路与读数仍可操作。无 Canvas／JavaScript 保留各自可用的静态阅读路径。仍为本地构建产物，未部署；客观验证与 owner 视觉接受分别报告。
- **生产接入未开始**：下一关是经操作者授权，用公开/合成案例进行有调用上限的真实采集，再按任务比较 baseline；私人上下文旁路验证需要单独确定输入边界。

命令以 [README](../README.md)、[next-action 说明](../experiments/next-action/README.md)、[typed-values 说明](../experiments/typed-values/README.md)和 [API 能力实验说明](../experiments/api-capabilities/README.md)为准。不要将 source、测试、真实推理或生产状态混为一谈。
