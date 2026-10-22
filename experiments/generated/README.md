# 原创有限世界生成与离线规则修复

这些题本用于检查实验基础设施和预先明确的机制假设。全部输入由标准库生成，不含私人材料；输出是 synthetic 或 imported evidence，真实 provider 一律 `NOT_RUN`。本目录不保存生成题本或真实运行记录，输出写入操作者选择的忽略目录。

`decision_lab/generators.py` 的 `generate_dataset(kind, seed=0, units=20)` 返回可直接 JSON 序列化的 `generated/v1` dataset。`units` 是独立 source families 的数量，不是展开后的行数；允许 1–10000，seed 必须为整数，不接受布尔值或浮点数。相同 kind、seed 和 units 的结果一致；增加 units 保留旧 families。四个 kind：

| kind | 每 family 变体 | 真值与变换 |
| --- | --- | --- |
| `probability` | 2 | 有限互斥世界的整数权重、精确有理数概率、loss matrix、每个动作的 expected loss 与全部 best actions；权重整体乘三不改真值。 |
| `documents` | 3 | 带显式版本的实体文档，最大版本优先；最小证据定位到最新文档。文档顺序不改答案；反事实配对保持 `entity/status` gold fields 完全相同，但 permit/deny 导致最优动作集合不相交，证明这个抽取 schema 不足以支持决策。 |
| `rules` | 2 | 交替生成 2/3 变量的完整有限真值表；自然语言采用可解析的显式正状态规则。候选表有一个错误，穷举给出二进制字典序最小反例；变量重命名不改函数。 |
| `geometry` | 4 | 整数轴对齐矩形的严格 `contains`、边界 `touching`、`disjoint`；颜色、平移、正比例缩放不改关系。部分面积交叠不在本题本支持范围，明确拒绝。 |

每行包含 `unit_id`、`source_family`、`latent_world`、`condition`、`replicate=0`、`seed`、`split`、`transformation` 和 `oracle`（包含 proof）。每 20 个 family 的固定槽位按 12/4/2/2 分为 train/dev/calibration/test，所有同 family 变体保留同 split；不足 20 families 时不保证四个 split 都存在。不要再按变体随机切分。`validate_dataset`（别名 `check_dataset`）重算 oracle、核对预期变换关系、family 完整性、稳定 split、metadata 与 request 投影。

`provider_request(row)` 只返回显式 `request` 投影；禁止发送完整 row/dataset。latent world、答案、proof、候选表和 oracle 不进入规则 provider request。规则本身必须描述目标行为，因此正状态规则作为任务输入存在；它与编辑用的答案表是不同字段。概率题的公开世界权重、loss matrix，以及文档和几何任务输入，是供推理的正常题干。

```python
import json
from decision_lab.generators import generate_dataset, validate_dataset, provider_request

suite = generate_dataset("rules", seed=17, units=20)
validate_dataset(suite)
request = provider_request(suite["rows"][0])
serialized = json.dumps(suite, ensure_ascii=False)
```

`decision_lab/rule_workflow.py` 的 `run_rule_workflow(dataset, ...)` 只接受 rules dataset，并只运行各 family 的 base 行，避免把变体当作独立证据。流程为 compile → 穷举全部状态 → 二进制字典序最小 counterexample → repair，直到全函数正确或 proposal budget 耗尽；`max_rounds` 代表初始 compile 后最多的 repair 次数。

- `compiler="exact"`：本地 solver 解析题干规则并产生完整表；`imperfect`：确定性翻转前两个状态，依反馈逐步修复；`memorize`：故意构造只记住反馈、不正确泛化的坏编译器，用来验证穷举检查能拒绝坏修复。
- `control="counterexample"`：反馈最小错误状态；`repeated-original`：重复原始题干，不提供反馈；`random-feedback`：按指定 seed 随机选择状态提供真值，不预先筛选错误。控制组使用相同初始 compiler，反馈机制分别运行，结果不预设优劣。
- `proposals={base_unit_id: [{"rule_version": 1, "truth_table": {"00": False, ...}}, ...]}` 导入完整、明确类型的 proposal 序列。必须恰好覆盖所有 base 行；每表穷举验证。导入只证明离线复算，不证明有真实模型采集。

每轮 trace 保留 proposal、来源、收到与发出的反馈、全函数正确性、Hamming distance/rate、关键状态 weighted loss 和所有检查状态。held-out 指本轮 proposal 从未收到反馈的状态，每次反馈后重新计算；它不是独立抽样数据集，也不证明编译器未从原始规则推导这些状态。split 则是 family 层独立保留的研究用途切分，两者不要混淆。

每个 family 还执行一次版本更新：翻转末状态并提升版本，检查旧 program 的 stale 标记，然后用本地新表确认验证可恢复。即使旧表碰巧全部输出正确，版本不匹配也不能判为全函数正确。开销分别记录 proposal 数、synthetic compiler 次数、导入次数、verification 状态求值次数、真实 provider 调用数（0），以及 N 次使用（`uses`）后的 `proposal_count_per_use`；计数针对 compile/repair 主路径，版本更新探针独立记录。latency/cost 为 `null` / `UNKNOWN`，没有凭空估价或把本地执行时间当成 provider latency。

```python
from decision_lab.rule_workflow import run_rule_workflow, replay_workflow

record = run_rule_workflow(suite, compiler="imperfect", control="counterexample",
                           max_rounds=8, uses=100, seed=17)
replay_workflow(record)
```

记录自含 dataset、configuration 和完整 trace。`replay_workflow`（别名 `validate_workflow`）重算完整执行并拒绝被改动的 proposal、反馈或指标。这里的 replay 校验内部一致性，不是外部签名或不可伪造的采集来源证明。不同 seed 或同 family 的变体不能冒充真实 provider 的独立重复运行。确定性 repair 成功仅证明本地机制可被穷举验证，不构成模型质量、模型效用、成本收益或生产效果证据。

针对性验证：

```bash
python3 -m unittest tests.test_generators tests.test_rule_workflow
```
