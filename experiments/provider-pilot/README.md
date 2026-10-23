# 原生 Decisions 首轮实验 · 2026-10-23

## Material Passport

- Origin：本项目的原创合成题本与有限世界；没有私人聊天、文档或真实业务记录。
- Mode：事前实验设计与有预算采集，protocol v1；不是模型排行榜或生产验收。
- 状态：**2026-10-23 已完成本轮有界采集与重放**；实际 541 attempts，包含 6 个 HTTP 404 与 2 个 uncertain。两个受隐私路由限制的条件没有正式采集，保留 planned missing；见[实测结果](#实测结果)。下文的 795 次是事前上限。
- 证据：首个 POST 前在本地冻结 protocol v1、manifest、调度、rubric 与源码差异；不是公开注册研究。原件、响应 bytes、attempt、版本化评分与回放保存在 Git 外的本机运行目录；不进入 Git 或站点。此页只公开设计、操作修订与合成任务的汇总。源码测试、契约预检、正式题本与账户观察分别报告。

这轮先回答三个可以用已有 oracle 判错的问题。接入检查仅决定某种原生契约能否进入对应实验，不根据预检答题表现筛选模型，也不把调用成功当成研究结果。后续更大样本、视觉 criteria、主动取证、寻址与完整 typed DAG 继续遵循[研究基础设施](../../docs/research-infrastructure.md)的独立门槛。

## 模型与主要比较

| 条件 | 固定请求模型 | 选择理由 |
| --- | --- | --- |
| CF Clef | `@cf/cloudflare/clef` | 主比较的较大模型，直接走 Workers AI |
| CF Clef Flash | `@cf/cloudflare/clef-flash` | 与 Clef 在同一供应平台和原生问题形式下配对 |
| OR Jev | `typesafe/jev-1.14` | TypeSafe 原生决策路线，经 OpenRouter 接入 |
| OR Luna | `openai/gpt-6-luna-decisions` | OpenAI 决策路线，经 OpenRouter 接入 |
| OR Mammoth free | `baseten/mammoth-1:free` | 一条明确标为免费的文本决策路线 |
| OR Mercury free | `inception/mercury-decide:free` | 不同作者的免费决策路线 |
| CF Clairic | `@cf/cloudflare/clairic` | 独立的 typed-values 实验，不能混入 Choice 排名 |

主比较预先固定为 **CF Clef 对 CF Clef Flash**；其余四个 Decisions 条件提供逐任务参照，不从所有两两比较中挑选显著结果。不同平台的模型、部署和服务契约一起变化，不能把观察差异单独归因为参数量、架构或路由。名称固定不代表权重 snapshot 已冻结；requested model、returned model、采集时间与 route 都保留。Clef Omni 不进入本轮；失败时也不自动换模型。

接口及目录依据：[CF Clef](https://developers.cloudflare.com/workers-ai/models/clef/)、[Clef Flash](https://developers.cloudflare.com/workers-ai/models/clef-flash/)、[Clairic](https://developers.cloudflare.com/workers-ai/models/clairic/)、[OpenRouter 原生 Decisions](https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request)、[Decisions 模型目录](https://openrouter.ai/api/v1/models?output_modalities=decisions)。这些来源只支持契约与当日目录事实，不证明账户可调用。

## RQ1：答案正确性与表示稳定性是否一致？

材料为既有三个已知世界的 27 个 probability cases，加 3 个显式 partition-events cases。每个条件重复两次，native body 完全相同，仅本地 request ID 和 replicate 不同。每模型 **60 requests / 102 questions**。

- 主要指标：明确数值答案相对 oracle 的事件概率 MAE，先逐次评分，再按世界等权聚合；正常数值答案的 conditional MAE 与包含失败的 workflow loss 并列。workflow loss 对计划但无可评分答案的题预先赋损失 1，不给它补数值答案；同时报告 planned、正常答案和失败分母。这衡量本次路线的完整工作流，不能把供应失败全部归为模型推理错误。
- 配对干预：逐字相同问题的单问／打包；边缘相同而联合不同的两个世界；粗／细区域菜单；显式 A、A1、A2、区域 B 的数值加法。
- 分开报告：数值误差、并／交／异或和区域加法违例、单问／打包差异、同题重复差异、原生菜单质量漂移。**菜单质量不是事件概率，confidence 也不是正确率。**
- 正负控制：同一保留 manifest 的 perfect、uniform、wrong synthetic oracle；分别证明评分能识别答对、无区分与一致但错误。oracle 不进入 provider 请求，也不与模型运行混算。
- 事前解释尺度：MAE 差异 0.05 是本轮关注的实际差异量级；同时对照原样重复的变化。小于该量级、或与重复变化相当的差异不据此宣称稳定优势。不是以该阈值筛选数据或追加采样。

三个世界不是三个世界各题数相加后的独立样本；两次重复也不增加独立世界数。本轮仅描述这三个构造上的结果，不输出总体 CI、显著性或概率校准保证，不把自洽改善等同于正确性改善。

## RQ2：规则的等价表示能否保留完整函数？

从既有 rule-compile 题本固定选择以下 33 cases，每模型重复两次，共 **66 requests / 66 questions**：

1. `r00` 至 `r15` 的 `w0-compile-baseline`，覆盖二变量全部 16 个布尔函数。
2. `r00` 至 `r07` 的 `w1-compile-baseline`，同时改变变量名和否定表述；这是联合改写干预，不能分离两个因素的因果效应。
3. `r00/r05/r10/r15` 的 `w0-compile-reversed` 和 `w0-compile-opaque`，分别改变候选顺序与 ID。
4. `rule-necessary-only`，正确结果是正常的 `insufficient` 选项，不能记成 API refusal 或 unknown。

主要指标为原始 16 函数的完整函数正确率；选中的函数在 `00,01,10,11` 上穷举，另报 Hamming loss 和反例。完整函数正确率以计划的 baseline 为分母，失败记为未正确；conditional 指标另列。缺函数的 workflow Hamming loss 记为 1，但不伪造一个错误真值表。改写、顺序和 ID 干预报告与匹配 baseline 的正确性及一致性，不能只因两次选同一错误函数就算成功。两次原样重复给出最小的运行变化观察；不据两次重复估计完整噪声分布。

主比较预先关注 2/16（12.5 个百分点）的函数正确率差异，并列每个反例，不做多重模型胜者检验。16 个函数是有限二变量空间的穷举，不代表一般自然语言规则。这里没有直接逐状态推理的等预算对照，因此不声称编译更便宜、更好或有真实摊销收益。

## RQ3：字段可提取是否足以完成任务？

Clairic 独立采集已有 7 个 typed-values cases，每例两次，共 **14 requests / 48 field trials**。保留来源缺失、Unicode 前缀、清晰／争议金额及两种区间案例。

报告摘录匹配、实体／版本正确性、原生 scalar null、direct / extracted-only / source-linked 的任务判断，以及区间覆盖与宽度。已知编辑答案和事后观测留在 rubric，不进入请求。原生 span 编码／端点约定未经核定时保留不确定性，不把所有错位归为模型错误。两条预测区间不足以估计覆盖率或校准；结果仅是案例观察。

## 预检、调度与停止

六个 Decisions 条件各使用既有四个原生 contract probes（Choice、Noul/Predicate、Score、混合题），共 **24 requests / 36 questions**；Clairic 另用一个公开合成 case 预检。每种 primitive 的兼容性独立报告。正式 RQ1/RQ2 只依赖 Choice；Score 或混合题失败不会被伪装成 Choice 质量问题。

| 部分 | 计划请求数 |
| --- | ---: |
| 六条件契约预检 | 24 |
| RQ1：30 cases × 2 repeats × 6 条件 | 360 |
| RQ2：33 cases × 2 repeats × 6 条件 | 396 |
| Clairic 预检与 RQ3 | 15 |
| **总 attempt 上限，包含失败** | **795** |

所有题面、候选顺序、rubric、主要比较与预算在首个 provider POST 前冻结；各条件保留同一逻辑 case/replicate。原生 route 的 dataset identity 仍分别保留，跨 route 的逻辑配对通过事前 case 映射显式核对，不跳过现有 identity 校验或冒称原生请求完全同构。

并发为 1；按预先固定 seed 对 case 顺序随机化，以 replicate 作为时间块，各时间块采用不同的模型顺序，记录开始／结束时间。这样减轻固定先后顺序的混杂，但不能消除服务变化、缓存或供应商内部路由。OpenRouter 免费调用遵守当日账户限制并限速；延迟只作观测，不以这轮安排宣称冷缓存 benchmark。

不自动重试、付费 fallback 或放宽隐私设置。HTTP、传输、原生解析失败保留 attempt 和耗时；缺失继续留在 planned 分母。预检中若某 route 的 Choice 契约不可用，停止该 route 的正式采集，保留预先计划的 missing；不能根据模型答对或答错提前停止。超时和 uncertain 不因恢复而重发。确属本地解析器问题时，只对已保留 raw 做离线修复与重放，不重新请求来替换旧证据。

事前本机独立预算为：**CF 本项目最多 4,000 Neurons，且账户当日免费余量必须另留至少 1,000；OR 本轮增量最多 $0.25，既有 key 上限仍独立生效**。CF 执行上限后续调整为 6,500，原因和时点见下方操作修订，不能把它冒充事前预算。余额、账户 ID 和凭据只在本机资源表与私有进程中使用，不写入此协议。输入估算不是账单硬上限；发送前为下一请求保留所选模型的保守费用空间，收到 usage 后记账，未知 usage 保守扣除而不按零计费。达到任一调用、输入、用量或金额边界即停止，未完成题数明确报告。

CF 免费额度是账户共享的 10,000 Neurons/day，在 00:00 UTC 重置；Workers Paid 超额会收费，不能仅凭每日刷新承诺零账单。执行前与阶段间刷新账户用量，保留其他项目和读数延迟的余量；不启用 AI Gateway Unified billing、不新增充值。规则与价格见[官方定价](https://developers.cloudflare.com/workers-ai/platform/pricing/)。预算不足时保留进度，下一免费窗口需要新的实际执行安排；本协议不创建自动续跑任务。

## 重放与结果边界

复用 `api-lab prepare`、`research probes/partition-events/plan/collect/ledger` 和 `typed-values` 的原生路径；运行记录中的请求与 rubric 拥有本次评分身份。[研究基础设施](../../docs/research-infrastructure.md)、[API 实验](../api-capabilities/README.md)、[typed-values](../typed-values/README.md)和[比较契约](../comparison/README.md)提供命令与详细定义。

主要结果先列各 route 的计划、尝试、HTTP 成功、原生契约有效和可评分题数，再列 RQ1/RQ2/RQ3 指标与反例。报告 failure-inclusive coverage 与 conditional quality，不丢弃失败。跨 route 分析只使用明确核对的同一逻辑 case；不能强行合并不同原生 dataset ID。原始响应与生成题本留在忽略的运行目录；公共文档只汇总不含凭据、账户信息的合成案例观察。

## 实测结果

日期为 2026-10-23（UTC+8），评分版本为 `api-capabilities/3`。以下结果来自这次真实原生 HTTP 采集，synthetic controls 不在其中。保留全部计划分母，未请求的题没有构造 provider 响应。

| 条件 | 正式计划 requests / questions | 含预检实际 attempts | HTTP 200 / 404 / uncertain | 正式正常 / 错误 / missing questions |
| --- | ---: | ---: | ---: | ---: |
| CF Clef | 126 / 168 | 130 | 129 / 0 / 1 | 167 / 1 / 0 |
| CF Clef Flash | 126 / 168 | 130 | 129 / 0 / 1 | 167 / 1 / 0 |
| OR Jev | 126 / 168 | 130 | 130 / 0 / 0 | 168 / 0 / 0 |
| OR Mammoth free | 126 / 168 | 130 | 130 / 0 / 0 | 168 / 0 / 0 |
| OR Luna | 126 / 168 | 2 | 0 / 2 / 0 | 0 / 0 / 168 |
| OR Mercury free | 126 / 168 | 4 | 0 / 4 / 0 | 0 / 0 / 168 |
| CF Clairic（独立） | 14 / 48 fields | 15 | 15 / 0 / 0 | 48 / 0 / 0 |

共 **541 attempts、758 个实际问题／字段槽、533 个 HTTP 200、6 个 HTTP 404、2 个 uncertain**。事前 1,096 个问题／字段槽中，746 正常、12 失败、338 未请求；其中 336 missing 来自两条未进入正式采集的路线，另 2 个是 Luna 未发送的预检题。所有已尝试 request ID 在各 job 内唯一；恢复只处理未尝试题，两个 uncertain 都没有重发。正常只表示原生契约可解析，不能读成答对。

四个实际进入 RQ1/RQ2 的条件均通过单题 Choice、Noul、Score 和混合题的契约预检。Luna 的预检响应明确报告 ZDR 路由冲突；Mercury 同时受免费端点训练政策和 ZDR 过滤约束。保留原隐私设置，没有换端点、付费 fallback 或改模型。正式质量指标对这两个条件为 **未测**；按协议计算的 workflow loss=1 和函数完成率=0 只表示本次计划没有获得答案，不能解释为模型推理质量。

实际返回模型分别为 `clef`、`clef-flash`、`typesafe/jev-1.14-20261014`、`baseten/mammoth-1-20261021` 和 `clairic`。这些是观测到的 label，不证明服务端权重、缓存或内部路由固定。

### RQ1：数值答案与菜单变化确实是不同对象

每条件计划的显式数值答案为 **84**：3 世界 ×（5 单问 + 5 打包 + 4 partition）× 2 repeats；其余 18 个概率题是 joint／coarse／fine 菜单。两次 uncertain 都发生在菜单题，因此四个条件的数值答案均为 84/84；本表的 conditional MAE 与 failure-inclusive 数值 workflow loss 相等，不能把菜单失败藏进这个等号。

| 条件 | 世界等权数值 MAE ↓ | 同题两次平均绝对差 | 单问／打包平均绝对差 | 有数值关系违例的组合 / 可检查组合 |
| --- | ---: | ---: | ---: | ---: |
| CF Clef | 0.004762 | 0 | 0.013333 | 2 / 18 |
| CF Clef Flash | 0.038095 | 0 | 0.013333 | 8 / 18 |
| OR Jev | 0 | 0 | 0 | 0 / 18 |
| OR Mammoth free | 0 | 0 | 0 | 0 / 18 |

一个组合为一个世界、一个 repeat 下的 single 事件向量、bundled 向量或 partition 向量。数值 MAE 按所有显式答案逐次计算再按世界等权；既有 evaluator 的按条件向量等权摘要权重不同，不用后者替换本轮主指标。Clef 三世界 MAE 分别为 0、0、0.014286；Flash 为 0、0.071429、0.042857（correlated、anticorrelated、split）。Clef 与 Flash 主指标差 0.033333，小于事前关注的 0.05；这里不据此宣布稳定优势。两次数值答案相同也不能推导服务确定性或冷缓存表现。

即使数值题全对，粗／细菜单仍有质量漂移：Mammoth 三世界的 coarse A − fine(A1+A2) 分别约 +0.1488、+0.2155、+0.4388；Jev 约 −0.215、−0.345、+0.055。每个值都有 2/2 配对；这描述候选菜单敏感性，**不是事件概率估计的错误**。Clef／Flash 在 correlated 世界各只有 1/2 个有效粗细配对，另一个保留为失败；不以另一 repeat 填补。原生概率与 confidence 均未重新归一化或解释成正确率。

### RQ2：原始函数答对，也不保证表示稳定

| 条件 | 原始 16 函数 × 2 正确 | 原始函数 workflow Hamming loss ↓ | w1 改写正确 | reversed 正确 | opaque ID 正确 | 必要条件不足时正确选 insufficient |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| CF Clef | 8 / 32（25%） | 0.453125 | 0 / 16 | 4 / 8 | 4 / 8 | 2 / 2 |
| CF Clef Flash | 6 / 32（18.75%） | 0.421875 | 0 / 16 | 4 / 8 | 4 / 8 | 0 / 2 |
| OR Jev | 32 / 32（100%） | 0 | 13 / 16 | 4 / 8 | 7 / 8 | 2 / 2 |
| OR Mammoth free | 32 / 32（100%） | 0 | 16 / 16 | 8 / 8 | 8 / 8 | 2 / 2 |

完整函数正确率以全部 32 个原始 baseline 为分母。合法的 `insufficient` 在完整规则题上仍会答错；没有可选函数时，Hamming workflow loss 按协议记为 1，不补造真值表。Clef 比 Flash 多答对 2/32，即 6.25 个百分点，小于事前的 12.5 个百分点；Hamming 指标反而是 Flash 较低，不能给出跨指标总冠军。

Jev 的原始函数全对，但倒序干预只有 4/8 正确。可穷举反例包括 `r05-w0-compile-reversed`：期望 `1010`，实际选中 `1100`，在 `01` 和 `10` 上相反；`r10-w0-compile-reversed` 期望 `0101`，实际 `0111`，在 `10` 上多判一个真。Clef 和 Flash 在原始 `r01` 两次均选 `0001` 而非 `1000`，于 `00`、`11` 错误。这些是原创合成规则上的观测，不是模型内部机制的解释。

有限函数配对的一致性也不能代替正确性：Clef 的 reversed 与 baseline 为 8/8 一致，却只有 4/8 正确；w1 与 baseline 的相同函数为 6/14 个有效有限函数配对，而 w1 正确为 0/16。Flash 的对应值为 8/8 一致、4/8 正确，以及 2/16 一致、0/16 正确。Jev 为 4/8 与 13/16；Mammoth 为 8/8 与 16/16。原样重复的有限函数配对：Clef 15/15（另 1 对两次均选 insufficient）、其余 16/16。没有从一致但错误的答案推导可靠性。

Mammoth 在本轮所有规则变体上均正确，支持把这条可用免费路线保留为后续对照。它没有证明对未见规则、真实材料或高风险决策可靠；这批已看过结果的例子应作为开发反例，后续评估必须另冻结新题本。

### RQ3：Clairic 的字段、缺失与下游任务

14 个正式请求、48 个原生字段均可解析；其中 44 个是有编辑答案的提取／数值字段，4 个是 estimate 字段。按冻结的逐值／整句 oracle，**38/44 精确匹配**。六处不匹配需要分开解释：

- `source-missing` 两次把归档订单日期 `2026-10-18` 填入当前订单的 date 字段；同一请求的文本日期证据字段却正确返回 null。原文没有当前订单日期，不能采用该 scalar，也不能用 confidence 消除实体冲突。
- 两个金额案例的 `status_evidence` 各重复两次，省掉了整句的版本前缀和句末标点，严格整句评分均未通过；摘录仍保留验收和争议的关键语义。这四处不能与错订单日期混称为六次事实错误。评分保持原样，没有看结果后放宽 oracle。
- 数量、单价、运费与总额在两个金额案例的两次重复中均与编辑答案等值，总额均为 1100 CNY。字段读取正确和任务完成仍分别报告。

把实际提取结果交给既有的**确定性下游 baseline**后，direct、extracted-only、source-linked 三路径的任务完成分别为 4/4、0/4、4/4。extracted-only 缺验收状态，合理地选择补材料；source-linked 可使用返回的状态摘录。这里没有第二个 decision model 的实测或完整 typed DAG，也没有随机因果比较，不能把 baseline 的表现计作模型完成任务。

两个区间案例各重复两次：wide 返回 median=5、[p10,p90]=[2,8]，宽度 6；narrow 返回 median=4、[2,6]，宽度 4。给定事后观测为 12 天，两种区间均未覆盖，历史 baseline [2,8] 也未覆盖；改变允许范围会改变答案，但 4 次观测来自两个相关构造，不能当成总体覆盖率或校准估计。span 的单位与端点约定仍未核定，不将其当作已验证的来源定位。

### 操作修订与复查

1. 首个请求前冻结 seed `20261023`；两个 replicate 内的 case 顺序分别用 seed 和 seed+1 shuffle。时间块模型顺序为：Luna → Mammoth → Clef → Mercury → Flash → Clairic → Jev；第二块为 Mercury → Clairic → Luna → Jev → Clef → Flash → Mammoth。预检失败者依规则跳过。中断恢复会打破原先连续的时间段，不能用此运行做无混杂的延迟比较。
2. 第 114 次派发后，checkpoint 写入路径短暂不可达，原因未核定；保留 Clef 一个 in-flight/uncertain 和完整费用预留，将运行原件逐字节核对后转到另一私有本机目录。为容纳该不确定预留，CF 项目上限从 4,000 调到 **6,500 Neurons**；账户另留至少 1,000 免费余量、OR $0.25、795 attempts、输入上限、模型、标签和重复均不变。这是执行修订，不能称为原始预注册预算。阶段读取的免费余量满足继续条件；账户读数留本机，不在此公开。
3. 第 225 次派发后，Jev 一个 17 项菜单的返回质量总和为 0.99，被本地严格 decoder 误报。独立核对 [OpenRouter 官方 SDK](https://github.com/OpenRouterTeam/ai-sdk-provider#evaluation)的两位小数舍入声明后，将 evaluator 从 `/2` 升为 `/3`：只对该 route 检查舍入网格与可能的总质量区间，原始值不变、不补成 1；CF 和直连接口不放宽。旧评价保留，从同一 raw 离线重算；标签、指标、请求和预算不改。已发送的 Jev 请求没有重发。
4. Flash 第二块发生一次 `ConnectionResetError`，保留 uncertain 与完整预留，随后只发送该 job 尚未尝试的 44 题。它和 Clef 的 uncertain 都在 correlated-fine 菜单题，正式覆盖各少一个正常答案；没有删除失败，也没有以另一重复补写。

已派发 attempts 的序列化输入合计 516,801 UTF-8 bytes（包含预检与失败），小于独立 1,000,000 bytes 上限。输入估算不是模型总 tokens 或账单；完整上下文的保守费用预留也不是实际扣费。没有自动重试、放宽隐私、充值、启用新的付费 fallback 或执行模型建议。

复查使用 retained collection 的 manifest、原始 bytes 与逐题评价；以 request/question/replicate 对齐，并先核对全部 attempt 和 missing，再核对 oracle 与反例。公共源题本、选择规则和评价器可供重做；真实原件保持本地，**这里不提供公开 raw 数据下载**。因此这是带本地可审计证据的首轮研究观察，不能冒充第三方已独立复现。
