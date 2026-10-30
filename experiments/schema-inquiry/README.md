# Schema 反例与主动核查

给定同一任务与有限世界，选择一个 schema 后，是否仍能为所有相同表示找到共同的最优行动？如果不能，哪条来源证据值得核查？本实验连接生成器的文档世界、schema 反例搜索与既有 E2 原生回合；不新增 provider transport。

## 从一个反例开始

默认表示保留 `entity`、`status`。两个世界都可表示为同一个目标实体、`ready` 状态，但现行条款分别为 `permit` 与 `deny`，正确行动是 `activate` 与 `hold`。添加 `current_policy` 可以区分这组世界；单独添加版本号不能区分同一版本号下的不同条款。

`schema_inquiry.audit` 按已知 source family 与所选字段分组，检查整组最优行动集合的交集，而非仅检查每一对。没有共同最优行动时，返回最少世界数的 witness（同规模按 ID 排序），以及候选可观察字段内所有 inclusion-minimal 修复集合。默认设计的来源文本与编辑真值由 `generators.document_oracle` 重算；通用 `audit` 的自定义行则依赖调用者提供的真值，不认证标注正确性。

搜索限于 128 行、每 family 最多 12 个世界和 8 个可观察字段，不证明开放文本中的一般充分性。没有找到反例只表示这份有限题本上存在共同最优行动。**字段是合成 oracle 投影，本实验不把它称为真实模型抽取结果。** E3 的原生抽取实验仍由 [Typed DAG](../typed-dag/README.md)拥有。

## 四类机制与成本

| Family | 初始信息与可得证据 | 精确控制应做什么 |
| --- | --- | --- |
| current-policy | 相同字段，现行条款相反 | 查询现行条款后决定 |
| version-binding | 旧版与邻实体干扰，现行记录可查 | 只采用目标现行条款 |
| unavailable | 现行条款未保留，所有可见字段均无法分辨 | 保留不确定，不为无信息查询付费 |
| already-sufficient | 旧版可以不同，现行行动在所有世界一致 | 直接采取共同最优行动 |

每类两个世界、先验各 0.5。设计要求至少两份版本不同的目标文档，使旧版与现行来源互不重叠。版本号最大的目标文档拥有当前条款；`ready` 不授予启用。错误终局代价 10、业务 `abstain` 代价 3、API failure／missing 保留代价 12。读取旧版与现行条款各花 1 个合成效用单位，预算 2、最多两次查询。这些单位不是美元，也不是 provider calls。

每条返回观察包含实体、版本、是否可得、精确 quote 和以独立文档为范围的 Unicode codepoint 半开区间。定位以文档为单位，避免旧版在整份材料中的偏移变化泄漏当前隐藏条款。不可得材料返回明确缺失，不能从 latent truth 补出 quote。完整原文中的缺失状态也保持缺失。

## 原生会话与完整原文对照

`compile_suite` 根据所选字段将相同投影编译为 E2 scenario。提供完整有限假设、查询观察映射和损失矩阵；选中的实际 world ID、witness、编辑正确动作及尚未揭示的实际来源不进入 adaptive body。这测量已知有限模型中的规划，不是开放调查。

`evidence-start/demo --query-mode read-all` 在首次原生判断前读取并计入全部本地查询；schema 题本同时向该原生请求提供可得完整原文。每个 episode 只有一次模型终局判断。`adaptive` 由模型逐轮选择查询或终止。两者保持同一 suite、planned 身份和损失规则，可由既有 `evidence-compare` 配对；记录明确区分本地读取次数与实际 provider requests。读取预算不足以覆盖全部材料时，read-all 拒绝启动。

每种 schema 在自己的投影组内重新条件化先验，报告按 scenario 等权，另保留 family 等权口径；`projection_group_prior_mass` 保留原分组质量。改变字段可能改变条件化分组，**不跨 schema 直接合并平均值或建立逐 episode 配对**。增加字段的代价也未由本题本估计，不能从“更多字段减少查询”推出免费收益。

```bash
python3 -m decision_lab research schema-design --output runs/schema-design.json
python3 -m decision_lab research schema-audit runs/schema-design.json
python3 -m decision_lab research schema-suite runs/schema-design.json --output runs/schema-suite.json
python3 -m decision_lab research evidence-demo --suite runs/schema-suite.json --output runs/schema-adaptive.json
python3 -m decision_lab research evidence-demo --suite runs/schema-suite.json --query-mode read-all --output runs/schema-full.json
python3 -m decision_lab research evidence-compare runs/schema-full.json runs/schema-adaptive.json
```

上述命令无网络。真实运行用 `evidence-start`、`evidence-prepare`、已有有界 collector、`evidence-apply` 循环，模型、输入与整轮预算须有对应授权。默认题本按两个字段的离线控制总损失为：立即停止 18、固定检查表／全部读取 22、一步／多步 oracle 10；分母都是 8 个世界。模型输出不会执行外部动作。

在[本地研究台](../../docs/studio.md)选择「字段还缺什么？」即可勾选字段、搜索反例、冻结、运行离线控制、导入原生轨迹与查看每轮剩余歧义、预算、quote 和原材料。研究包及 raw responses 只保存在本机；公开研究采用[独立日期协议](pilot-2026-10-30.md)和汇总。
