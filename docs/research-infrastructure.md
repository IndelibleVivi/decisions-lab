# 可追溯的研究实验

本轮研究基础设施把测量、重复试验、失败与最终损失接起来。默认操作全部离线；只有 `research collect` 和旧 `collect-live` 是显式开启的网络入口。源码和本地假服务验证不证明 provider 可用或模型效果，题本状态仍为 **NOT_RUN**。

## 从一个反例开始

世界概率为 `00=.2, 01=.2, 10=.3, 11=.3` 时，粗菜单中 `A={10,11}` 最可能，细菜单中 `B={00,01}` 最可能。每题都答对的 one-hot oracle 可以得到 `r(A)-r(A1)-r(A2)=1`。这是答案菜单效应，不能被解释成事件概率不一致。事件概率的误差与加法关系只从明确的数值答案计算；原生 option mass、confidence、正确率和行动损失分别报告。

```bash
mkdir -p runs/research-inputs
python3 -m decision_lab api-lab prepare --experiment probability --route decisions --replicates 2 > runs/research-inputs/probability.json
python3 -m decision_lab research oracle --manifest runs/research-inputs/probability.json --mode perfect --run-dir runs/perfect-001
python3 -m decision_lab research oracle --manifest runs/research-inputs/probability.json --mode wrong --run-dir runs/wrong-001
python3 -m decision_lab research ledger runs/perfect-001 --output runs/perfect-ledger.json
python3 -m decision_lab research compare runs/perfect-001 runs/wrong-001
```

默认 probability 与历史10-22 retained manifest 均保留27 requests/39 questions；独立 `research partition-events --route decisions` 为三个世界新增3 requests/12道显式区域数值题，每题写清状态集合。这样数值加法与众数菜单效应分别采集，重放不从当前生成器重造。`perfect`、`uniform`、`wrong` 都是本地构造的 oracle 控制，不是模型结果。重复调用的 native body 相同，request ID 与 `trial.replicate` 不同。同一逻辑槽位 `(unit_id, condition, replicate, question_id)` 不允许被两条请求覆盖。旧 manifest 没有 trial 时使用明确的兼容身份；歧义重复会拒绝，不能猜测重复编号。

## 原生证据与外层账本

`api-lab` 的 manifest/record、typed-values 的字段记录、next-action 的 action 记录各自拥有原生语义。`research ledger` 只读这些文件并重算已有评分，产生 `decisions-lab.run-ledger/1` 视图。它列出每个 planned question 的 trial、结果和引用，以及独立的 request metrics，不改写旧文件。collector 在同一外层保留 attempt，仍由原评分器解释答案。

| 对象 | 真源与意义 |
| --- | --- |
| dataset | API 的 model-neutral 身份包含题面、问题顺序、rubric、headers、route 与 trial，排除 model；改输入不能继续冒充同一题本。不同原生 route 暂不自动宣称同构。 |
| trial | `unit_id/source_family/condition/replicate/split/seed`，以及 request/question ID。变体与独立世界分开。 |
| planned set | api manifest 的全部 requests；typed record 的 selected IDs；新 next-action record 的 `planned_case_ids`。未计划不进入分母，计划但无结果为 missing。 |
| legacy | 没有 planned set 的旧 next-action 文件保守按全题本显示 missing，并明确无法恢复当时 subset 意图。新旧 reader 不回填未知运行事实。 |
| attempt | 开始/结束时间、单调计时、HTTP 状态、原始 bytes 的 base64、独立 JSON parse 状态、delivery、retry reason、usage/cost。 |
| evaluation | raw 与评价分离；api replay 保留当次 manifest。typed 字段值和 null/guess 保留；estimate 不伪造二元 correctness，其原生值和区间评价单列。 |

`research compare` 需要预先定义的 loss 或 boolean correctness；不能把 forecast/estimate 或任意 score 自动变成正确率。没有可比较的 loss 时会明确拒绝。next-action 的旧 `replay` 仍检查当前 adapter；跨默认模型历史读取使用 `research ledger` 的只读兼容器，检查支持的旧请求结构与保留的 requested model，不改变历史文件。

## 有预算的采集与恢复

先准备固定请求，再计划、检查预算，最后由操作者明确选择是否调用。下面前两步均离线：

```bash
python3 -m decision_lab research probes --route decisions --output runs/contract-probes.json
python3 -m decision_lab research plan --kind api-lab --manifest runs/contract-probes.json --output runs/probe-plan.json
python3 -m decision_lab research plan --kind typed-values --case-id source-missing --output runs/clairic-plan.json
```

最小 API probes 包括 Choice、Predicate/Noul、Score 的单题和混合题，共 4 requests/6 questions。它检查基本 wire contract；Jev 图片沿原视觉题本准备，不把图片 criteria 当作 OpenAI 图像输入。高题数边界、cache 和区域支持仍需另定 probe 和预算。Clairic 直接保留题本字段与官方 REST envelope；[官方模型页](https://developers.cloudflare.com/workers-ai/models/clairic/)与[OpenAI create reference](https://developers.openai.com/api/reference/resources/decisions/methods/create)是接口依据，不是服务端实测证明。

真实调用必须另行明确模型、公开/合成输入与上限。将凭据放到运行环境：OpenAI 为 `OPENAI_API_KEY`，Jev 为 `TYPESAFE_API_KEY`，Clairic 为 `CLOUDFLARE_API_TOKEN` 和 `CLOUDFLARE_ACCOUNT_ID`。不加载 env 文件，不把认证 header 写入结果，固定官方 HTTPS endpoint，不跟随 redirect。账号标识和真实运行目录保持本地，不进入 Git 或站点。

```bash
# 仅供已获本次真实调用授权的操作者使用；本项目尚未执行此步骤
python3 -m decision_lab research collect runs/probe-plan.json --run-dir runs/probe-live-001 --allow-network --max-calls 4 --max-questions 6 --max-estimated-tokens 20000 --timeout 30
```

目前并发固定为 1，按固定 seed 交错请求顺序。请求数、题数、输入 token 估算三项预算覆盖所有 attempts，包括重试与不确定发送。token 估算采用序列化输入的 UTF-8 bytes，是本地调度约束，**不是 provider tokenizer、输出 token 限额或账单上限**。输出 token、cache 与实际费用只记录 provider 报告的事实；不从价格表补账单。相同货币且每次 attempt 金额明确时才累加 cost，任何未知项保持 null。

每次发送前先保存 `in_flight`；HTTP、parse、transport、cancel 分开。429 仅在显式 `--max-attempts > 1` 且总预算仍足够时重试，默认每题一次；其他失败不自动重试。JSON 无效仍保存原始 bytes；timeout、取消和进程中断可能意味着 provider 已收到请求，delivery 标为 uncertain。

trial 评价使用该 planned request 最后一次 attempt，前序失败仍完整留在 attempt 轨迹及总耗时/费用中；它们不冒充独立 replicate。比较器的失败分母指最终未得到正常结果的 planned trial，瞬时失败与最终恢复分别可查。

`--resume` 使用同一 plan、endpoint 和预算恢复；读取、校验和写入 checkpoint 都受 `.collector.lock` 保护。已完成请求不会再次发送，uncertain 默认跳过。确需重新发送时增加 `--retry-uncertain`，它明确承认潜在重复执行/计费，不能保证 exactly-once。`--max-attempts` 是每请求总尝试上限；预算耗尽不通过恢复清零。预算配置是历史计划的一部分，恢复不能暗中扩大。

Ctrl-C 或 run 目录下的 `CANCEL` 文件使本地停止并保存已有尝试；当前 HTTP 请求受 timeout 约束，无法保证撤销 provider 工作。硬退出可能遗留 lock，先确认原进程已停止，再手动移除 stale lock；不能仅因等候较长就移除。`settled` 只表示计划的请求都有 attempt，不表示每题成功或质量合格。失败重放和 missing 分母由 ledger/comparison 展示。

冷/热缓存条件、跨时间块的正式调度、输出 token 硬限制、实际账单对账和多并发尚未实现。started_at、seed 与 request 顺序已可追踪；它们本身不构成缓存收益实验。

## 生成、验证与比较

```bash
python3 -m decision_lab research generate --kind rules --seed 17 --units 20 --output runs/rule-worlds.json
python3 -m decision_lab research rule-workflow --dataset runs/rule-worlds.json --compiler imperfect --control counterexample --output runs/rule-repair.json
python3 -m decision_lab research rule-replay runs/rule-repair.json
```

四种生成器覆盖精确概率/行动损失、实体版本文档、有限布尔规则、几何关系；每例带真值证明、source family、固定 split 与变换关系。文档世界提供“gold fields 完全相同，最优动作集合却不相交”的 schema 不充分反例。生成器不等于这四类任务的模型 runner；发送只能使用显式 request 投影。完整 API、约束和有限正状态规则语法见[生成与规则修复](../experiments/generated/README.md)。

规则链保留 compile→穷举→最小反例→repair 全轨迹，比较 counterexample、重复原题、随机反馈；区分全函数正确、Hamming、关键状态损失、未见反馈状态、版本过期与 N 次使用的 proposal 摊销。exact/imperfect/memorize 都是本地 solver 或 synthetic 控制，也接受离线导入的版本化 proposal。没有假称这些控制的改进就是模型收益。

比较按逻辑 trial 配对，对 unit 等权，再按 source family 做 cluster bootstrap。失败/missing 留在 workflow loss 分母，conditional accuracy 单列；少于 8 个 family 只给描述结果，不输出总体 CI。risk–coverage 同分数一起接纳，缺 score 不补零。calibration 选阈值，test 只评估；plan 固定比较、指标和 failure loss，软件不能证明操作者此前未看 test。见[比较与统计](../experiments/comparison/README.md)。

```bash
python3 -m decision_lab research freeze-plan --dataset-id <dataset-id> --left <left-run-id> --right <right-run-id> --failure-loss 1 --output runs/analysis-plan.json
python3 -m decision_lab research compare <left-record> <right-record> --analysis-plan runs/analysis-plan.json --failure-loss 1
```

## 研究方向与后续门槛

本次优先建立 W0 测量、W1 身份账本、W2 有界采集基础、W3 生成与 W4 比较，并贯通 E4 离线路径。有限 oracle 不提供真实模型、外部迁移或生产结论。历史研究日期和原始结果保留。

| 方向 | 现在可用 | 尚待检验及下一门槛 |
| --- | --- | --- |
| E1 表示与决策 | 数值/菜单语义分离、oracle、重复、有限概率损失世界 | 全面 clone/无关选项/正控制与通用模型等预算对比；效应需超过原样重复底噪，且不能以一致性提高代替 regret 降低。 |
| E2 主动取证 | 版本文档与证据集作为输入资产 | 查询环境、错误承诺/有效追问/恢复成本、检查表对照；一步 VOI 与 XOR 信息互补的有限预算多步 oracle 分开，尚无 runner。 |
| E3 信息保留与组合 | 既有 direct/extracted-only/source-linked；新 schema 不充分配对反例 | 完整串行 DAG、gold 抽取/计算/检索逐层干预、等 token 普通摘要对照，避免将下游失败都归因抽取。尚未实现此 DAG。 |
| E4 可验证规则 | 2/3 变量生成、穷举、反例修复、版本探针、导入/replay | 自然语言必要/充分/例外/量词、分层Choice/8 bits/DSL 的真实模型比较；有限正状态语法不代表一般规则编译。 |
| E5 寻址与上下文 | [既有研究设计](api-capabilities.md#semantic-addressing) | flat/逐段/树/beam/BM25/embedding 的等访问预算，完整证据 recall、首错剪枝、无答案误命中和最终损失；尚无控制器。路径分数乘积不是联合正确率。 |
| E6 图像规则 | 既有定义交换题本；新几何关系不变性资产 | 跨形状/旋转/边界/文字冲突、像素相似与颜色基线；Box 先判断存在再评定位，尚无新增视觉 provider runner。 |
| 特征、分布、实时与 HCI | [既有七方向设计](api-capabilities.md) | 特征仅在训练/开发提出并冻结；分布保留成熟/删失、覆盖与宽度；Live先做状态版本/乱序回放；HCI固定AI输出并保存独立/最终判断，测纠错、错误跟随与验证成本。均未开展实际实验。 |

公开真实材料迁移、真实调用、有限样本风险保证、Learn then Test、多重比较及停止规则的自动执行仍未实现。下一次采集先冻结主要比较、最小有意义效应、数据 split、预算与停止依据，再执行授权范围；不能因新 API 或价格变化重写旧结论。
