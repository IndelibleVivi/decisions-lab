# 当前状态

更新时间：2026-10-24。

- **Luna 原生补测已完成**：[独立日期报告](../experiments/provider-pilot/luna-followup-2026-10-24.md)保留新设计、130 次 HTTP200／174 问、三世界 MAE 0.0333333 与原始函数 2/32；首轮隐私失败不改写。OpenAI 分组 ZDR 临时例外已获操作者精确授权，全部 Luna 请求已停止；浏览器控制故障使恢复尚待操作／读回，不能声称已恢复。没有调用 ChatGPT 订阅或 Nous。
- **角色题本与部分实测已完成**：[独立说明](../experiments/decision-roles/README.md)拥有四类 16 worlds、三表示、两重复及同输入 policy；新 `research role-scenarios/role-report` 复用 api-lab/collector，分别计算 retained loss、完整 planned 分母、unsafe 与 guard 拒绝。五条件计划 480 attempts，已采集 384 次且全 HTTP200；Jev/Luna/Mammoth 各 96 次完成，Clef/Flash 各 48 次，剩余 96 因本机 Keychain 凭据读取失败未发送，保留 checkpoint，不是日免费限额。原设计及原始响应保留，下一步只恢复这两个未尝试 block；私人项目 mapping 与真实输入不进入公开题本。

- **首轮原生实验已完成有界采集**：[协议与实测](../experiments/provider-pilot/README.md#实测结果)记录 541 attempts、533 HTTP 200、6 个隐私路由 404、2 个保留且未重发的 uncertain。Clef／Flash／OR Jev／OR Mammoth 各 126 次正式尝试；Clairic 14 次正式请求。Luna／Mercury 没有正式结果，保留 planned missing。三世界数值题、16 原始函数及变体、7 个 typed cases 都按冻结设计逐次评分；不是排行榜、生产验收或总体校准证据。两项执行修订和中断恢复均如实记录；原始响应、manifest 和账户观察不进入 Git 或站点。
- **原生接线与研究基础设施已验证**：[方法与命令](research-infrastructure.md)提供oracle构念控制、显式trial/replicate、planned/missing、只读legacy账本、api-lab/Clairic有界collector、四类分组生成器、配对比较与少簇限制。api-lab 已贯通 CF Clef／Flash 和 OR 原生 Decisions，OR 新请求默认使用本轮可调用的 Mammoth free；evaluator `api-capabilities/3` 处理 OR 声明的两位小数舍入，保留原值及旧评价，不放宽其他路线。规则编译→穷举→最小反例→修复及版本探针仍是离线synthetic/导入路径；首轮没有测模型修复收益或缓存收益。collector 保留 bytes、失败耗时和 uncertain，输入估算不提供账单硬上限。
- **API 能力依据已整理**：[10-22 定向核查](../research/2026-10-22/README.md)记录 16 项来源、8 条变化，核对 OpenAI reference／SDK 差异、Jev 原生图片标准和多题 context、Clairic 表示族、Live 与 Clef-Omni 条件。历史 census 与既有增量保留日期，不重新核价。
- **能力研究有明确入口**：[7 个能力方向](api-capabilities.md)与[可查询索引](../catalog/capabilities.json)连接来源、假设、对照、指标和本地覆盖。规则编译、概率组合、视觉 criteria 的离线 `api-lab` 已实现原生多题请求、导入、独立评分与快照 replay；首轮仅实测文本固定 subset，视觉与其余完整方向仍无 live 结果。历史题本保留 NOT_RUN authoring 状态。新日期的旧 12 probes 是设计修订，不是本轮已执行的原生契约预检。

- **研究可读**：首期日期快照、23 个实体、21 个项目、171 条来源索引与 6 项研究已整理；不是所有来源在本轮重新审查。
- **定向更新已整理**：[10-15 增量](../research/2026-10-15/README.md)记录 30 条来源、12 条变化，覆盖 Jev 1.14、OpenAI Decisions 文档／SDK 差异及 Cloudflare、Fastino、Upstage。历史快照保留，未重查全量目录。
- **Clairic 增量已整理**：[10-20 调查](../research/2026-10-20/README.md)记录 8 项官方来源、7 项变化；原始 schema 和官方示例固定 revision，四条 Cloudflare 路线的标价按本轮日期记录。旧增量可以用 catalog 的 `--date` 查询。
- **类型化输出工具与首轮采集已完成**：[方法章](typed-values.md)和[三组实验](../experiments/typed-values/README.md)包含缺失值、提取后计算及上下文损失、区间评估。`examples.json` 的 7 个原创草案、编辑答案和 authoring NOT_RUN 状态保留，真实 Clairic 运行独立记录；14 次正式请求的 48 fields 均可解析，38/44 个有真值字段严格匹配，缺失日期存在两次错实体填值。三路径使用确定性 baseline，没有第二个模型或完整 typed DAG；少量 estimate 不提供总体校准。span 约定仍未核定。独立 CLI 的离线准备、demo、导入与 replay 均保留。
- **玩法可探索**：[20 种配方](playbook.md)按六组组织，每项给输入、选项、现成项目、第一步与失败方式；两项已有离线实验，其余是接入提案。项目来源各自标日期，原创玩法不冒充上游已有功能。
- **历史可复算**：随包 1,000 个案例、4,000 条概率记录的复算与基准结果一致，14 项作者汇总核对一致。原始输入不随项目分发。
- **离线实验已实现**：25 个原创合成 next-action 用例、确定性 baseline、含错误和 unknown 的 demo、记录与完整性校验 replay。
- **next-action API adapter 候选**：TypeSafe Jev 与 OpenAI Decisions 原生 contract；继续固定 `jev-1.13.0` / `gpt-6-luna` 的现有文本 Choice profile。增量文档不自动启用 Box、图像、cache 或新版模型。文档核对与 mock 测试不等于真实 API 可用，live 推理未运行。
- **阅读站源码已更新**：27 页从 Markdown/catalog 构建；首轮、Luna 补测与角色实验页进入显式 allowlist，运行记录保持排除。首屏粒子作品和标题直接操控保留；下方由像素卡带、稀疏信号场、PLAY 招牌轮播和自托管字体构成。unknown 从编号动作中独立出来，ok／unknown／refusal／error 的文字、画面与结果读数同步；后两类为明确标注的离线示例，没有选中动作或实际请求，不产生概率与 confidence。分类、搜索、fragment、任务 JSON 复制、项目入口、概率示意、历史矩阵与三例练习均保留。下方共享暂停联动招牌、图标、信号场和实验动态；减少动态、后台、离屏停止，静态选路与读数仍可操作。无 Canvas／JavaScript 保留各自可用的静态阅读路径。仍为本地构建产物，未部署；客观验证与 owner 视觉接受分别报告。
- **生产接入未开始**：有界合成实验已有真实结果；新角色题本已冻结且部分采集，当前关口是恢复未尝试的两个 CF block，并核定临时隐私例外恢复；表示敏感性与缺失值错误继续分别研究。私人上下文旁路需要单独确定输入边界，没有自动执行、日续跑、充值或部署。

命令以 [README](../README.md)、[next-action 说明](../experiments/next-action/README.md)、[typed-values 说明](../experiments/typed-values/README.md)和 [API 能力实验说明](../experiments/api-capabilities/README.md)为准。不要将 source、测试、真实推理或生产状态混为一谈。
