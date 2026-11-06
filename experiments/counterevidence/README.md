# 反证调查台

初步结论可能正确，也可能沿用了过期、错实体或遗漏例外的材料。模型需要决定是否核查来源、核查哪一份，以及什么时候作出决定或保留不确定。

本实验复用 E2 的有限世界、状态机、原生 api-lab 请求、有界 collector 和完整 planned 分母。`decision_lab/counterevidence.py` 拥有题本与可见投影；`evidence_workflow.py` 仍拥有 prepare/apply/replay。Studio 的入口位于原首页实验 D，没有新增 provider 服务。

## 模型看见什么

模型收到任务规则、目标对象与时间、带有初步结论的材料、核查入口与成本、剩余预算，以及实际查询后得到的来源摘录。它不会收到实际 world、完整假设表、精确后验、未揭示的来源、编辑真值或本地评分。两个隐藏世界的初始模型输入相同，只有查询后的实际观察可以使它们分开。

规则由题本明确规定；来源的实体、适用时间、发布者权限和条件共同决定效力，不能以“最新文本”替代适用性判断。材料和规则都是原创合成内容，不是现实法律意见或真实机构政策。

旧 E2 和 schema inquiry 提供完整有限环境与精确后验；本题本只向模型展示材料。因此不能将两类实验直接合成同一能力成绩。有限 oracle 仍可使用完整环境计算策略，**其额外信息必须与模型条件分开解释**。

## 条件与测量

| 条件 | 输入与动作 | 原生请求 |
| --- | --- | --- |
| `no-query` | 只看初始材料，作出决定或暂缓 | 每 episode 一次 |
| `adaptive` | 逐轮选择核查，观察实际证据后决定 | 随实际轨迹变化 |
| `read-all` | 先揭示全部可得观察并记入读取成本，再决定 | 每 episode 一次 |

默认每次查询成本 1、错误承诺 10、业务暂缓 3、API failure 12，最多三次查询。损失是合成效用单位，不是美元。读取成本、终局损失、错误承诺、暂缓、API unknown/refusal/error、planned missing、原生请求数和 usage 分别保留。未完成回合不跳过，uncertain 不自动重发。

轨迹检视展示初始材料、实际所选查询、来源摘录与 locator、终局动作和局部诊断。“行动与初步结论不同”只表示可观察的动作关系，不等于模型承认错误或内在信念更新。有限模型中的无信息查询诊断由本地环境计算，不进入 provider body；真实材料中的一般充分性不由这份题本证明。

## 离线运行

```bash
python3 -m decision_lab research counterevidence-design --output runs/counterevidence/design.json
python3 -m decision_lab research counterevidence-suite runs/counterevidence/design.json --output runs/counterevidence/suite.json
python3 -m decision_lab research evidence-demo --suite runs/counterevidence/suite.json --output runs/counterevidence/oracle.json
python3 -m decision_lab research evidence-report runs/counterevidence/oracle.json

python3 -m decision_lab research evidence-demo --suite runs/counterevidence/suite.json --query-mode no-query --policy stop --output runs/counterevidence/stop.json
python3 -m decision_lab research evidence-demo --suite runs/counterevidence/suite.json --query-mode read-all --output runs/counterevidence/full.json
python3 -m decision_lab research evidence-compare runs/counterevidence/full.json runs/counterevidence/oracle.json
```

以上为明确标注的 synthetic 控制，无网络或凭据读取。真实工作流使用 `evidence-start --suite ... --route decisions --model gpt-6-luna`，随后沿用 `evidence-prepare` → [有界采集](../../docs/research-infrastructure.md#有预算的采集与恢复) → `evidence-apply`。每一轮只发送 retained request 的 body，不能发送整份 suite、manifest 或研究包。

在[本地研究台](../../docs/studio.md)装入「反证调查台」，编辑条件、冻结后运行离线对照或导入原生记录。全部条件共享冻结题本，导入按 query mode 严格绑定；重开、派生、研究笔记、历史解释器复现和当前重分析仍走现有路径。模型请求需要单独的当轮输入与预算授权，Studio 本身不读取 key 或调用模型。

## 证据与限制

[2026-11-06 首轮协议与中止报告](pilot-2026-11-06.md)保留冻结设计和首次 HTTP503 停止事实。[11-07 续采与结果](continuation-2026-11-07.md)只补未发送请求，保留原失败后完成 72 个终局记录：adaptive 与 full 的逐样本终局动作相同，分别读取 36／40 次材料，却用了 60／24 次原生调用。六类有限机制、重复及跨日期续采只支持题本内分析；不把重复当作新的独立来源，不报告一般模型排名或开放调查能力。初步结论的可靠性未知不等于已实现任意错设概率模型的恢复；本实验测的是可见材料下的核查与停止行为。

当前原生 API 只返回列出的动作，模型自由文本解释不是本实验产物。模型建议不执行外部系统；公开页面只分发合成设计与汇总，运行目录、原始响应、operator、源码冻结和账户计量留在本机。
