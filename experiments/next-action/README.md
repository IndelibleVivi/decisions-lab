# next-action 实验：为供给文档/变更推荐下一步阅读动作

本实验研究：给定一份**公开文档或变更**，以及**任务/主张（claim）上下文**，
模型应推荐哪一个下一步「阅读 / 核对」动作。实验只输出建议，**永不执行**该建议，
也不改动外部系统。所有用例均为**原创合成**任务，未复制任何 benchmark 数据集。

## 动作契约（精确含义）

- `inspect_source`：到文档明确指向的来源（diff、commit、上游页面）核对原文事实。
- `compare_contract`：对照调用方/接口契约，判断这次变化是否改变签名、字段、语义或兼容性。
- `read_in_context`：结合当前调用方或运行上下文，判断该变化是否真正适用。
- `needs_more_context`：现有输入缺失或含占位符，无法下判断；必须先补齐上下文。这是
  **正向任务动作**。
- `unknown`：请求中显式提供的**保留判断选项**，表示没有任何提供的动作适配当前输入；它不是第五个可执行动作。模型**显式**
  选择它时才算 `unknown`。它既不是 `needs_more_context`，也不是接口拒答（refusal），
  更不是运输错误（transport error）；四者分别记录。缺失 choice 是格式错误，不视为 `unknown`。

一个用例可以有**多个**可接受动作（`acceptable` 列表）。当多种动作都站得住脚时，
本实验不会捏造唯一正确答案。

## 数据与切分

- `cases.json`：25 个原创合成用例，含中文、英文、中英混写、缺失来源/上下文、
  否定/条件变更、同名不适用、以及多可接受动作等情形。
- 每个用例声明：稳定 `id`、`source_group`、`split`（`dev`/`test`）、任务输入
  （`task`）、可接受动作集合（`acceptable`）与编辑理由（`rationale`）。
- **同一来源的语言变体始终归入同一 `source_group` 与同一 `split`**；校验会拒绝
  跨 split 泄漏。
- 标签/harness 元数据（`id`、`split`、`source_group`、`acceptable`、`rationale`）
  **绝不进入** provider 请求，也绝不作为 baseline 输入。只有 `task` 内容模型可见。
- 数据来源：项目原创合成；不采集私有 chat、账号、凭据或个人路径。

## 运行命令（离线为默认）

```bash
# 0) 默认 suite 已内置：validate / demo / replay 可省略 suite 参数
#    （等价于 experiments/next-action/cases.json）
python3 -m decision_lab validate

# 1) 校验用例 schema、取值、id 唯一、来源组切分、非空可用
python3 -m decision_lab validate experiments/next-action/cases.json

# 2) 确定性保守规则 baseline -> 记录一次合成运行
python3 -m decision_lab baseline-run experiments/next-action/cases.json \
    --run-dir runs/next-action/baseline-001

# 3) 离线合成演示：含一个「故意判错」与一个「显式 unknown」示例
python3 -m decision_lab demo --run-dir runs/next-action/demo-001

# 4) 从已记录响应离线重放并评估（无需网络）
python3 -m decision_lab replay runs/next-action/demo-001
#    可选：仅在显式选择阈值时，用已记录的 maxP 统计量做选择性覆盖评估
python3 -m decision_lab replay runs/next-action/demo-001 --threshold 0.6

# 5) 请求准备：为两条路线生成原生请求体（无网络）
python3 -m decision_lab prepare experiments/next-action/cases.json --route jev --limit 2
python3 -m decision_lab prepare experiments/next-action/cases.json --route decisions --limit 2

# 6) 查看已编码的路线画像与来源状态
python3 -m decision_lab routes
```

### 记录目录约定

- 记录写入**全新的**本地运行目录下的 `record.json`；已存在且非空时**拒绝覆盖**
  （除非显式 `--clobber`，且仍拒绝写入 `catalog/`、`research/`、`experiments/`、`tests/` 源目录）。
- 构建输出与真实运行记录不提交。

## 路线与请求/响应契约

两条**原生**路线，请求/响应形状不同，各自保留原生语义。字段形状已于
**2026-10-09** 由协调者对照官方文档逐字段核对（**文档证据**，非 live 证据；
本轮未对任一 provider 发出请求）。

| route key | 提供方 | 固定模型 | 官方文档 | 端点 | 概率字段 | 选择字段 | confidence 字段 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `jev` | TypeSafe 原生 System One | `jev-1.13.0` | https://docs.typesafe.ai/api | `POST https://api.typesafe.ai/v1/systemone` | `answers.next_action.probabilities` | `answers.next_action.choice` | `answers.next_action.confidence` |
| `decisions` | OpenAI 原生 Decisions | `gpt-6-luna` | https://developers.openai.com/api/docs/guides/decisions | `POST https://api.openai.com/v1/decisions` | `answers[].probabilities[].probability` | `answers[].choice` | `answers[].confidence` |

**请求**（无顶层 request id；操作性 ID 只保留在本地）：

- TypeSafe：`{"model":"jev-1.13.0","state":<任务输入对象>,"questions":{"next_action":{"type":"choice","instructions":<问题/评分标准>,"criteria":{option_id: description, ...}}}}`。
- OpenAI：`{"model":"gpt-6-luna","input":<序列化任务输入字符串>,"questions":[{"type":"choice","name":"next_action","instructions":<评分标准>,"choices":[{"value":id,"description":description}, ...]}]}`；没有 `decision` 对象、`allow_unknown` 标志或顶层 `metadata`。

两条请求都向**全部选项**提供有意义的描述：四个任务动作 `inspect_source` /
`compare_contract` / `read_in_context` / `needs_more_context`，**外加显式的
`unknown` 保留判断选项**（无自造的 abstain 字段）。`unknown` 表示没有提供的动作适配当前输入；
`needs_more_context` 仍是**正向任务动作**，二者不同。

**响应**（保留原生形状与原生 confidence，另存 `raw`）：

- TypeSafe：`{"model":str,"answers":{"next_action":{"type":"choice","choice":id,"probabilities":{ALL option: float},"confidence":number}},"usage":{input_tokens,output_tokens}}`。**TypeSafe 文档没有 refusal 字段**，本项目不发明；未支持形状按错误处理。
- OpenAI：`{"answers":[{"type":"choice","name":"next_action","choice":id,"probabilities":[{"value":id,"probability":number}],"confidence":number}]}`。refusal 是 `type:"refusal"` 的 answer，与 choice 分开保留；**不发明顶层 refusal**。

> **来源状态**：`python3 -m decision_lab routes` 报告
> `docs_verified_at: 2026-10-09` 与 `live_verified: false`。这是文档核对，不是
> live 证据：API 可用性、模型质量与实际价格均未被断言。任何未来文档漂移都会在
> 归一化时以严格校验错误暴露，而不会被静默误读。

[2026-10-15 定向核查](../../research/2026-10-15/README.md)记录 Jev 1.14、OpenAI reference／SDK 差异及新请求示例。这里仍固定原有 `jev-1.13.0` / `gpt-6-luna` 文本 Choice profile，不因 alias 变化升级，不接入图像、Box 或 cache。更换模型后必须独立记录运行条件；新增文档没有更新此 adapter 的实测状态。更多任务设计见[玩法大全](../../docs/playbook.md)。

校验规则：确有唯一的问题标识、只含已知选项、数值有限且落在 `[0,1]`
（拒绝 NaN/Inf/bool）、按文档容差近似和为 1、选中项等于 argmax（容差内允许并列）；
OpenAI 的数组值重复即拒绝。**不做重新归一化**。缺失 choice 视为**格式错误**，
绝不视为 `unknown`。原生 confidence 与 `maxP` **分别保留**；返回的 `model` 作为
实际值保留，**不发明**单独的 model_version。

归一化保留：路线专属语义、原生概率/置信度（**不发明统一置信度公式**）、原始响应
（`raw`）、返回的模型、以及类型化的 unknown / refusal / error 结果。

## live 收集（需显式授权；默认不执行）

该命令已实现，供**未来获授权的操作者**运行；本轮**未执行**。

```bash
export TYPESAFE_API_KEY=...   # 或 OPENAI_API_KEY
# 注意：--max-calls 必须 ≥ 计划调用的用例数。默认 suite 有 25 个用例；
# 若只想跑一部分，必须显式 --case-id 选择，否则会因用例数超出上限而被拒绝。
python3 -m decision_lab collect-live experiments/next-action/cases.json \
    --route jev \
    --run-dir runs/next-action/live-001 \
    --case-id relnote-field-zh \
    --case-id relnote-field-en \
    --max-calls 2 \
    --timeout 30 \
    --allow-network
```

安全约束（代码内强制，测试覆盖）：

- 固定官方 HTTPS 端点；凭据只来自环境变量；**凭据绝不写入记录**（Authorization 头从不进入记录）。
- 必须显式 `--allow-network` **且** 正数 `--max-calls`；默认命令离线。
- 有界超时；读取响应体有上界（`MAX_RESPONSE_BYTES`）；**无隐式重试**；**无 provider fallback**。
- **拒绝重定向**，避免 `Authorization` 泄露到其他主机；异常路径也始终关闭连接。
- 运输/HTTP/解析失败仍产生**可审查**的记录，且记为非选择的错误——绝不记为成功，
  也绝不编造成本。
- 记录**保留每个用例的实际出站请求**（端点 + 精确请求体），**每次尝试都保留**，
  包括运输失败。重放时把保留请求体与该用例重新绑定校验，因此**篡改的请求体或
  静默的适配器漂移会被拒绝**，而不是被静默信任。凭据/头不进入记录。
- 运行时**逐用例写入检查点**（原子替换：临时文件 + rename，因此中断不会破坏上一份
  有效记录）。但这**只是可审查，不是自动 resume**：重放可做覆盖检查，**重试需要新的运行目录**。
- 输出到全新本地运行目录；拒绝覆盖；拒绝写入 `catalog/`、`research/`、`experiments/`、`tests/` 源目录。
- 无 env 文件加载、无后台守护、无自动任务发现。

## 重放与评估语义

- 完全离线，基于**实际记录的响应**。
- 检测并拒绝：缺失用例、重复用例、外来（不在 suite 中）用例、以及任务/路线/模型
  请求上下文不匹配（用例内容摘要变化）。**绝不把子集静默当作完整评估**。
- **记录完整性校验**：拒绝被污染的记录——outcome 与 action 不一致（例如 error/refusal
  带 action、unknown 被标为正确、ok 用 unknown 动作）、概率非有限或不在 `[0,1]`、
  分布不近似和为 1、选中项不是分布 argmax、confidence 非有限或超出 `[0,1]`。被篡改的记录不会被计为正确。
- **保留请求绑定**：live 记录为每个用例保留实际出站请求体与端点。重放时校验其仍等于
  当前适配器为该用例生成的请求，因此篡改的请求体或静默漂移会被拒绝；仅离线 baseline/demo 可不保留出站请求；live 缺失请求会被拒绝。凭据/头从不保留。
- 记录链接确切输入/用例/协议，保证可复现；除摘要外还保留精确出站请求体。
- 区分：正确性覆盖、已尝试失败、unknown/refusal 比率、选择性覆盖（实际作答占比）。
- 阈值覆盖只统计正常作答，不把 unknown/refusal/error 算作可采用动作。
- 概率仅在**显式选择阈值**时评估，并使用有文档的统计量（`maxP`），**绝不使用统一置信度**；
  阈值必须有限且落在 `[0,1]`。
- 用量/成本按**实际报告**展示，缺失时为 null/unknown；展示观测延迟；
  **不把价格表算术当作观测账单**。
- CLI 对畸形/不完整输入给出可读错误并非零退出。

## 反例与失败可见性

`demo` 命令构造两个可见反例：

1. 一个**故意判错**的答案（`correct=false`）——让读者看到一次失败判断；
2. 一个**显式 unknown** 的答案——它与 refusal、transport error 分别记录。

demo 中所有响应都标记为 `synthetic: true`，是**合成构造**，**不是模型推理**。
baseline 准确率只是合成演示，不构成模型质量、API 可用性或真实价格声明。

demo 记录中的每个结果都带一个覆盖**全部五个提供选项**的合成分布（合法分布：有限、
在 `[0,1]`、和为 1，且 argmax 等于所选动作），以便读者看到完整选项形状。

## 输出与安全/隐私边界

- 记录目录含：`record.json`（run 元数据 + 每个用例的结果；live 结果含保留的端点与
  精确出站请求体、收到的 HTTP status 与解析后的原始 JSON；无响应时 status 为 null，**不含**认证请求头）。
- 不记录认证请求头或私有 continuity。记录包含 suite 路径、任务输入与 provider 返回内容；使用私人输入时，这些记录也属于私人数据，默认留在被 Git 忽略的 `runs/`。
- 离线演示、fixture 验证、HTTP 模拟与真实 provider 调用**分别报告**。
- 测试与 CI 不使用真实凭据、不调用模型；HTTP 模拟在运输边界完成。

## 测试

```bash
python3 -m unittest discover -s tests -p 'test_lab*.py'
#   或统一入口（离线）：
python3 tools/check.py --core-only
```

覆盖：标签泄漏拒绝、畸形/错误响应归一化、伪造的「缺失数据成功」、重复 id /
来源组切分泄漏、unknown/refusal/error 混淆、不安全的 redirect/retry 行为、
覆盖拒绝、以及离线命令不触发网络。
