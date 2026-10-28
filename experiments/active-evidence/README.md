# 主动取证：从下一步建议到完整决策

本实验研究：缺少信息时，选择一个具体问题是否改善最终决定，收益是否足以抵偿查询成本？状态、可获得证据、先验、损失和预算都来自原创有限世界。环境与原生逐轮接线已实现；[10-28 首次 provider 实验](pilot-2026-10-28.md)完成三模型、184 次请求和 96/96 episodes。它给定完整假设表和精确后验，结论限于已知有限模型中的 planning fidelity。

`decision_lab/evidence.py` 拥有有限环境、oracle 与评分；`evidence_workflow.py` 将每轮接到既有 api-lab manifest、原生记录和 collector。query 只揭示本地合成世界的一条观察，commit 只结束实验，不操作外部系统。没有新 transport 或自动网络循环。

[首次原生实测协议](pilot-2026-10-28.md)固定已知有限世界中的 planning fidelity 问题、完整分母、对照与消费上限；事前设计与采集结果分别报告。

## 为什么需要多轮

一次请求里的多个问题共享输入。后一个问题若需要读取前一个返回的新信息，必须准备后续请求。这里每轮只发送当时的 visible state，收到动作以后才改变下一轮输入。相同可见历史的两个 hidden worlds 得到相同请求 body；actual world ID、未揭示的实际观察与本地评分不进入 body。

环境公开完整的**假设表**：各可能世界的先验、每个查询在该假设下的结果、各 terminal decision 的损失。隐藏的是本次选中了哪个世界。因此这是已知有限模型下的部分可观察决策实验，不是开放网页搜索、未知观察模型或通用自然语言调查的仿真。

实际路径为：

```text
冻结 suite / planned episodes
  → visible state → 原生 manifest → api-lab record 或有界 collector
  → 校验本轮回答 → query 揭示观察 → 下一轮 visible state
                    commit / abstain / API failure → 终局报告
```

suite、planned world、rubric 和回合关联保留在本地。模型看到的只是 `requests[].body` 和该请求所需的非秘密 header。整个 manifest 含本地真值，不能整体发送。

## 设计与对照

默认生成 7 个机制 family、16 个 world episodes；每次 replicate 完整枚举同一组世界。seed 仅改变呈现顺序，不增加独立来源。

| family | 要区分的机制 |
| --- | --- |
| `key-evidence` | 一条关键证据足以改变决定 |
| `xor-complement` | 两个单独无价值的问题，合起来才有价值 |
| `uninformative` | 询问无关索引只增加成本 |
| `robust-stop` | 未知细节不影响所有相容世界共同的最优动作 |
| `unavailable` | 材料缺失且不可取得，查询不能补出事实 |
| `asymmetric-prior` | 非均匀先验与非对称错误代价改变选择 |
| `stale-entity` | 旧版／邻实体材料与目标现行材料的区别 |

四种 synthetic policy 消费相同可见契约：

- `stop`：按当前后验，立即选择期望损失最低的 terminal decision 或业务暂缓。
- `checklist`：按固定公开顺序查询仍合法的问题，随后按后验停止。它可能浪费查询预算。
- `myopic`：比较查询成本加“一问以后立即停止”的期望损失，只在严格更好时查询；每个后续回合重新计算。
- `optimal`：穷举有限预算、相容世界和剩余查询的完整策略树。平局优先停止。

`robust_actions` 是所有相容世界中最优 terminal decision 集合的交集，独立于 Bayes 风险准则。不能把“当前期望风险可接受”写成“证据已经稳健充分”。

XOR 控制中，两问各花 1 单位，查询预算为 2，错误承诺损失为 10，业务暂缓损失为 3。myopic 立即暂缓，总损失 3；optimal 先问两次再正确决定，总损失 2。这是精确有限世界的控制结果，不是模型实验结论。方法与外部来源见[研究主线](../../docs/research-programme.md)。

## 五分钟离线跑通

所有命令均在 repo 根目录运行，Python 3.11+，仅标准库。每次输出使用新路径，禁止覆盖旧记录。

```bash
# 冻结原始设计；只写 runs/ 或 repo 外的新文件
python3 -m decision_lab research evidence-suite --output runs/evidence/suite.json

# 相同设计的两个确定性完整策略
python3 -m decision_lab research evidence-run --suite runs/evidence/suite.json --policy myopic --output runs/evidence/myopic.json
python3 -m decision_lab research evidence-run --suite runs/evidence/suite.json --policy optimal --output runs/evidence/optimal.json
python3 -m decision_lab research evidence-report runs/evidence/optimal.json
python3 -m decision_lab research evidence-compare runs/evidence/myopic.json runs/evidence/optimal.json

# 连续经过原生请求、synthetic response、逐轮 apply 的完整路径
python3 -m decision_lab research evidence-demo --suite runs/evidence/suite.json --route decisions --policy optimal --output runs/evidence/native-demo.json
python3 -m decision_lab research evidence-report runs/evidence/native-demo.json
```

默认完整 demo 经过 3 轮：较早结束的 episode 不再请求，XOR 两次 query 后才 commit。`decisions`、`jev`、`clef`、`clef-flash` 和 `openrouter-decisions` 都复用现有原生准备规则；CF 需要 `--account-id`。离线支持一个 route 不证明该账户可调用。demo 的 one-hot probability / confidence 只是合法原生格式的 fixture，不用于校准，也不产生真实 latency、usage 或费用。

## 准备、导入与继续

```bash
# 固定路线和模型；没有读取凭据或网络
python3 -m decision_lab research evidence-start --suite runs/evidence/suite.json --route decisions --model gpt-6-luna --output runs/evidence/state-0.json
python3 -m decision_lab research evidence-prepare runs/evidence/state-0.json --output runs/evidence/round-0.json

# 外部响应按 api-lab 的原生导入格式准备，并绑定本轮 manifest
python3 -m decision_lab api-lab import --manifest runs/evidence/round-0.json --responses <本轮响应.json> --run-dir runs/evidence/import-0
python3 -m decision_lab research evidence-apply runs/evidence/state-0.json runs/evidence/import-0 --output runs/evidence/state-1.json
python3 -m decision_lab research evidence-prepare runs/evidence/state-1.json --output runs/evidence/round-1.json
python3 -m decision_lab research evidence-report runs/evidence/state-1.json
```

重复 prepare → 本轮采集／导入 → apply，直到 prepare 输出 `null`。state 文件是新的不可覆盖快照，包含原始 suite、planned episodes 和已经应用的原生记录；派生状态由 replay 重建。旧回合、别的 episode、改过请求或已经应用的回答不能作为当前回合继续。

一次 apply 是**整回合原子操作**。少一个 response／answer、仍有 `in_flight` 或 delivery uncertain 时拒绝应用，原状态不变；先回到原 collector 处理其 checkpoint。已明确结束的 API error、unknown 或 refusal 会成为对应 episode 的 failure，区别于业务 `abstain`。本实验不提供失败后的自动重问或人工改选；要研究这些恢复策略，需另定义预算、状态和比较条件。

若另有本次模型、输入和预算的真实调用授权，可以先将本轮 manifest 交给 `research plan --kind api-lab`，再用既有[有界 collector](../../docs/research-infrastructure.md#有预算的采集与恢复)。把其 run 目录作为 evidence-apply 的 source；不需要导入第二份 response。网络开关、凭据、调用／题数／输入估算上限和 uncertain 恢复规则仍由 collector 拥有。每轮的 collector 预算只约束该轮；**当前没有跨轮账单硬上限或自动全程调度器**，操作者必须在完整协议中分配总预算。

默认不联网；本实验说明不授权模型调用。原始响应、含账号的 endpoint、实际输入及运行 state 不进入 Git 或站点。

## 记录、评分与解释

- `evidence-suite/1` 冻结任务；每题最多 16 个 hypotheses、8 个 queries、16 个 decisions，查询不能重复。完整 schema 名均带 `decisions-lab.` 前缀。
- `evidence-run/1` 保存 synthetic policy 的完整 planned set 与 action/observation history；缺失和中断仍用冻结的 failure loss，已花查询成本保留。
- `evidence-workflow/1` 保留原生 api-record／collection 回合，重新解码再重建状态，不信任缓存分数。digest 检查一致性与回合绑定，不是签名或 live 来源证明。
- `evidence-report/1` 分别报告实际 terminal loss、query cost、total loss、query count、错误承诺、暂缓、API failure、missing、决定覆盖、每次查询前后的风险与 family 汇总。query cost 与 terminal loss 使用同一个合成效用单位；它们不等于 token 或账单。
- 等 world 行均值和按先验加权结果分开。枚举所有世界不是按先验抽样；非均匀先验不能被行数隐式改写。repeats 不增加独立来源数。
- 标准 policy 的完整 tree 可以计算 expected regret。任意模型轨迹只观察了部分分支，完整 policy expected regret 保持 `null`；实际路径上的 conditional action regret 另列，不用 realized loss 减 expected optimum 冒充它。
- 原生 request、attempt、usage、latency 与 cost 按请求归属，不能复制到每个查询或题目再累加。缺失费用保持 `null`，只有同货币且全部已知才汇总。synthetic 不提供真实调用用量。
- `evidence-compare` 要求完全相同的冻结 suite 与 planned 身份，逐 episode 配对、保留全分母，并给出 family 分组。`evidence.left/right` 同时保留 synthetic/imported/collector 来源、原生 route/model 与逐轮 source records；来源未知仍是 null，比较不证明 live 调用。这批有限机制不输出总体置信区间。

本实验走出了静态 next-action 的一步答案，首次实采已经显示有限已知模型中的规划差异；开放语义取证、等 provider calls 因果比较、外部资料迁移、人类实验与生产采用仍无证据。独立 [Typed DAG](../typed-dag/README.md)接续研究抽取、计算与下游信息保留，其 provider 研究尚未运行。后续先固定主要比较、等调用／等成本安排和未见机制；不能在看到结果后更改成本或真值。
