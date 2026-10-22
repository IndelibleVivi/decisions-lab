# 离线配对比较与选择性预测

`decision_lab/comparison.py` 比较两个 normalized common run ledger，不调用 provider。数据输入为 `schema: decisions-lab.run-ledger/1` 的 JSON object，`trials` 列出全部 planned trials；`metadata.dataset_id` / `metadata.run_id`（也接受顶层同名字段）关联题本身份与 run。只有 manifest 身份时不能将含 model 的 manifest 当作跨模型题本身份。已知的两个 dataset_id 不同会拒绝比较。

每个 trial 包含 `request_id`、`question_id`、`unit_id`、`source_family`、`condition`、`replicate`、`split`、`outcome`，以及 nullable 的 `correct`、`loss`、`confidence`、`latency_ms`、`cost`。`outcome` 是 `ok`、`unknown`、`refusal`、`error`、`missing` 之一。正常答案需有 `loss` 或 boolean `correct`；两者均未知时无法计算 workflow loss，函数拒绝产生貌似完整的评分。`correct: null` 不转换成错误标签；有数值 loss 而没有 correctness 时仍可比较 workflow loss，但 error loss 与 conditional accuracy 不虚构答案。

## 配对、分母与估计

```python
from decision_lab.comparison import compare_runs

report = compare_runs(left, right, split="test", seed=0,
                      bootstrap_samples=2000, failure_loss=1.0)
```

以 `(unit_id, condition, replicate, question_id)` 配对，request/model 可以不同。同一 run 出现重复 key 时拒绝；同 unit 的 source family 映射不一致、同 source family 跨 split、两 run 间源族或 split 映射冲突时也拒绝。验证在筛选前进行，筛选不能隐藏这些冲突。可用 `split` 与 `condition` 筛选；未筛选的结果不应当作 held-out test 结论。

比较使用两个 planned key 集合的并集。只出现在一侧的 key 在另一侧补记 `missing`，两侧均按完整并集分母计分；报告同时保留 `paired`、`left_only`、`right_only` 和每个 trial 的 `trace`。这类结果明确是含 missing counterpart 的完整 workflow 比较，不能将并集数量宣传为完整观测的配对数量。两侧都未写入的 planned trial 无法从空白中恢复，输入 ledger 必须显式枚举它。

默认 metric 是 `workflow_loss`：`ok` 优先用显式 `loss`，没有显式 loss 时取 `1 - correct`；所有其他 outcome 使用预先指定的 `failure_loss`，包含 unknown/refusal/error/missing。调用者应在看 test 结果前确定 failure loss 的业务意义。可传 `metric="error_loss"`：正常答案取 `1 - correct`，失败使用相同 penalty；此时所有正常答案必须具有 correctness。`conditional_accuracy` 单独报告，只以正常且 correctness 已知的答案为分母；它不能替代包含失败的 workflow loss。

`left` / `right` summary 是 trial 描述统计，`estimate` 是主要比较估计：先将每个 `unit_id` 的所有 condition、variant、question 和 replicate 等权平均，再对 unit 等权平均。因此一个 unit 多写 variants 不会获得额外独立样本权重。主要 delta 固定为 `right - left`，正值表示右侧 loss 更高。`units` 与 `trace` 保留汇总和原始 trial 的关联。

CI 采用 source-family cluster percentile bootstrap：以 family 为单位有放回抽样，带回该 family 的全部 unit，计算抽中的 unit 平均 delta。各 family 大小可以不同，bootstrap 的估计对象仍是 unit 平均量。默认 2,000 次、固定 seed，输入排序不影响结果。少于 8 个 family 时只输出 `descriptive-only`、`ci95: null` 和原因；`min_clusters` 只能向上调整。8 不是可靠性的保证：依赖结构、抽样框、分布外转移及样本代表性仍决定解释范围；CI 不证明模型在真实部署中的风险或因果效果。family 之间的独立性由数据设计保证，软件不能从标签证明它。

## Usage 不重复累计

`requests` 数组是 request-level latency/cost 真源，按 `request_id` 唯一；若未提供，兼容地将 trials 按 request 去重，并拒绝同一 request 的已知 metrics 冲突。一个 request 回答多个 question，其 usage 只计一次。筛选结果只统计触及这些 trials 的完整 request，不估计某个 question 分摊了多少 usage。

只有全部相关 request 的 latency 已知时才报告总计和平均，否则保持 null 并报告已知数量。只有全部 request 的 cost 均为 `{amount: number, currency: string}` 且 currency 一致时才求和。bare number、currency 不明、混合 currency 或任一未知 cost 均保持 `cost_total: null`；不使用模型标价补齐，不换汇。输入 metrics 是 run 的记录事实，不代表实测价格或当前 provider 报价。

## Confidence、ties 与 calibration

`risk_coverage(rows)` 返回各个有效 confidence threshold 的累计点。同 confidence 的 ties 一起接纳。只有 `ok`、correctness 已知、有效 `[0,1]` confidence 的 trial 可以接纳；unknown、没有 score 的答案、调用失败都不会被补成零 confidence。coverage 分母始终是全部 planned trials；risk 是已接纳答案的错误率，loss 是已接纳答案的 workflow loss，两者分开。无有效 score 返回空曲线。

```python
from decision_lab.comparison import select_threshold, evaluate_threshold

selection = select_threshold(calibration_rows, target_risk=0.10)
test_report = evaluate_threshold(test_rows, selection)
```

阈值只能从全部标记为 `calibration` 的 rows 选择，取经验 risk 不超过目标的最高 coverage 点；不存在可行点时返回 `threshold: null`、`reject_all: true`。评估只接受 `test` rows 及 calibration selection object，并拒绝 calibration/test 使用相同 source family。零接纳时 coverage 为零、risk/loss 为 null。不得看 test 再选 target、threshold、模型或 metric；这里的经验约束没有 finite-sample risk guarantee，也没有实现 conformal risk control。

## 冻结 analysis plan

```python
import json
from decision_lab.comparison import freeze_analysis_plan, compare_runs

plan = freeze_analysis_plan(
    dataset_id="example-suite-v1", comparison=["left-run", "right-run"],
    metric="workflow_loss", failure_loss=1.0, split="test",
    condition=None, calibration_split="calibration", threshold=None,
)
# 在查看 test outcome 前将 plan 保存到独立分析目录；已有文件应拒绝覆盖。
with open("analysis-plan.json", "x", encoding="utf-8") as stream:
    json.dump(plan, stream, ensure_ascii=False, indent=2)
report = compare_runs(left, right, plan=plan, failure_loss=plan["failure_loss"])
```

plan 绑定明确 dataset_id、左右 run_id、metric、failure penalty、test split、condition、unit 聚合、cluster 和 delta 方向。comparison 的左右顺序有意义。`compare_runs` 验证身份与参数，并自动使用计划内 split/condition；显式冲突参数拒绝。确认性 plan 固定 calibration/test 分离；`threshold_selection_split: test` 不允许。若传入从 calibration 冻结的数值 threshold，比较时低于 threshold 或 confidence 未知的正常答案会归为 unknown，依预定 failure penalty 计入全部分母；trace 保留原 outcome。阈值可取 `select_threshold` 的非空结果，但 reject-all selection 应使用 `evaluate_threshold` 报告，不能把 null 当作比较阈值。

plan 是可检查的预先约定文件，软件不能证明文件创建时间、题本标签真实性或操作者此前没有查看 test。修改计划或事后探索应保存为独立分析并标为 exploratory，不能覆盖原计划伪装预注册。本模块不自动写文件，也不上传 trial 或 analysis plan。

## 本地验证

```sh
python3 -m unittest tests.test_comparison -v
```

测试只使用合成 ledger，覆盖 null/已知效应、cluster 内相关、unit variants 权重、少簇、顺序不变、missing/失败分母、ties、校准与 test 分离、frozen plan、unknown cost、request 去重。它们验证离线统计契约，不是 live provider 测量或模型能力结论。
