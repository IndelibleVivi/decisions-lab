# 材料充分性与待核实提示

本实验交叉控制两个因素：关键事实是否已出现在材料中，以及同一份材料是否附带“待核实”警告。目标是观察首次查询与暂缓选择如何变化，不推测模型的内在信念。

`decision_lab/inquiry_framing.py` 拥有新题本、四条件投影、最多两轮的工作流和专用配对报告。原生请求、响应解析和网络采集复用 `api_lab`／`collection`；CLI 默认离线。旧反证调查题本与评分保持其冻结契约。

## 四种条件

| 条件 | 初始材料 | 待核实提示 |
| --- | --- | --- |
| `sufficient_neutral` | 规则及足以唯一决定的完整记录 | 省略警告字段 |
| `sufficient_warning` | 同一完整记录 | 加入警告包 |
| `missing_neutral` | 同一记录缺少关键事实 | 省略警告字段 |
| `missing_warning` | 同样缺少关键事实 | 加入警告包 |

警告包仅在 `initial_dossier` 增加 `provisional: true` 及固定的 `notice`；neutral 不额外断言材料已核验。剥离这两个字段后，同一题、同一材料条件的原生输入必须完全一致。这个因素是两字段的组合，不区分其中某个词或布尔字段的单独作用。

八组原创新题各有允许／不允许两个世界；每世界默认重复两次，四条件共 128 个 planned episodes。隐藏关键事实后，同一题的两个世界给模型相同输入。完整记录必须足以根据公开规则确定决定。世界 ID、标准答案、评分和未揭示事实只在本地保留。

所有条件都有相同的封闭查询契约：查询只返回本题同一份记录的完整副本，不存在其他文件、更新或隐含条件。因此完整材料下查询会重复已有内容；缺关键事实时查询会补足该事实。这是在有限环境中检验停止，不代表开放调查。

首次动作可以决定允许、不允许、暂缓或查询；仅真实选择查询的 episode 会准备下一次终局请求。终局只能决定或暂缓。每 episode 最多两次原生请求，查询成本 1、错误决定 10、暂缓 3、API failure 12，都是合成效用单位。

## 判读

主要测量是首次查询率，同时保留首次暂缓、无充分依据直接决定、正确直接决定及各类 API 结果。材料齐全时仍选择查询只是本契约下的重复读取行为；不能直接归因模型内部机制。

报告警告在两种材料条件中的配对差异、缺关键事实在两种提示中的配对差异，以及二者的差中差。每组新题独立列出结果；世界与重复相关，不将 128 当作独立真实文档样本，也不输出总体显著性或泛化区间。缺失、uncertain、unknown、refusal、error 均不补成“没有查询”；未完整观察的相关效果保持未知，并显示完整 planned 分母。

终局行为、读取成本和 provider 用量是次要结果。后续调用只发生在选择查询的样本上，不能只比较这个选择后的子集并冒充随机对照。首次选择和完整 episode 结果分别保留。

## 使用

```bash
python3 -m decision_lab research framing-design --output runs/framing/design.json
python3 -m decision_lab research framing-demo --design runs/framing/design.json --policy oracle --output runs/framing/oracle.json
python3 -m decision_lab research framing-report runs/framing/oracle.json

python3 -m decision_lab research framing-start --design runs/framing/design.json --model gpt-6-luna --output runs/framing/state-0.json
python3 -m decision_lab research framing-prepare runs/framing/state-0.json --output runs/framing/round-0.json
```

有独立模型／输入／预算授权后，准备结果接到[既有有界 collector](../../docs/research-infrastructure.md#有预算的采集与恢复)。仅发送每条 retained request 的 body。收到原生 collection 后：

```bash
python3 -m decision_lab research framing-apply runs/framing/state-0.json runs/framing/collection-0 --output runs/framing/state-1.json
python3 -m decision_lab research framing-prepare runs/framing/state-1.json --output runs/framing/round-1.json
```

如有后续请求，按相同流程采集、apply，再 `framing-report`。`framing-demo` 支持 `oracle`、`always-query`、`stop` 三种显式 synthetic 控制，均不读取凭据或调用模型。日期实采见 [11-07 协议与汇总](pilot-2026-11-07.md)；原始轨迹、冻结源码及 operator 留在 Git 和站点之外。

部分 collection 也可以 apply 并查看完整分母报告；missing／uncertain 留为待处理，`framing-prepare` 会拒绝新一轮。只能在原 retained collector 中按其恢复约束补齐或解决，再 apply 同一轮的新快照；已经收到的响应不能改写。每条原生请求的 attempts／usage 只计一次，未知费用保持 `null`，synthetic 和 imported 记录不证明真实调用。revision 1 固定这八组题本；`seed` 保留为排序用的设计元数据，实际发送顺序由 collector 的 `seed` 控制，不随机改写题目或真值。
