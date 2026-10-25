# Decisions Lab

**把判断与取值，变成可以检查的实验。**

[English](README.en.md) · [研究主线](docs/research-programme.md) · [主动取证](experiments/active-evidence/README.md) · [研究基础设施](docs/research-infrastructure.md) · [API 能力实验](experiments/api-capabilities/README.md) · [类型化输出](docs/typed-values.md) · [妙妙玩法](docs/playbook.md) · [当前状态](docs/current-state.md)

Decisions Lab 研究 decision models 与类型化取值：从证据中选择动作、提取字段、计算数值，或估计尚未确定的结果。我们关心接口承诺了什么、错误发生在哪里，以及怎样把判断接入一个仍由人和代码负责的工作流。

这里有三种不同寿命的内容：可持续使用的方法、带日期的调查、可以重新运行的实验。版本和价格会变；当时的来源、请求和结论不应跟着消失。

## 从接口能力走向完整决定

我们持续研究：结构化输出保留了什么意义，它能否改善后续决定？日期调查提供来源，有限世界和干预使主张可判错，原生请求与完整失败分母使结果可回看。[研究主线](docs/research-programme.md)连接这些能力、当前证据和下一阶段门槛。

[主动取证实验](experiments/active-evidence/README.md)已将“下一步问什么”贯通为 query → 揭示观察 → 后续原生请求 → 最终决定。7 个机制 family、16 个隐藏世界分别研究关键证据、XOR 信息互补、无关查询、稳健停止、不可得证据、非对称代价和旧版本干扰。检查表、立即停止、一步 VOI 和完整多步 oracle 使用同一可见契约；回放保留查询成本、终局损失、暂缓、API failure 和 planned missing。原生逐轮接线复用 api-lab 与有界 collector，默认完全离线；本题本尚无 provider 质量结果。

```bash
python3 -m decision_lab research evidence-demo --route decisions --policy optimal --output runs/evidence-native-demo.json
python3 -m decision_lab research evidence-report runs/evidence-native-demo.json
```

这里的响应由确定性控制合成，演示完整多轮数据流，不调用模型。真实采集须另行固定模型、输入和全程预算；query 仅揭示本地合成观察，不执行外部动作。

## 能力研究与日期依据

[10-22 核查](research/2026-10-22/README.md)把 API 能力接到可证伪的实验：一次 Choice 编译布尔规则、比较概率的粗细分类与联合关系、用参考图片重定义 Jev criteria。独立的 `api-lab` CLI 处理原生多问题请求、离线响应导入、分题评分与反例报告。题本真值来自穷举、已知世界和几何生成规则；synthetic demo 不代表模型表现，历史题本保留 `NOT_RUN` authoring 状态，新的真实运行独立留证。[能力方法章](docs/api-capabilities.md)保留 7 个研究方向的对照与实现边界；[能力索引](catalog/capabilities.json)可以离线查询来源、假设、指标和请求覆盖。

[10-20 调查](research/2026-10-20/README.md)加入 Cloudflare Clairic，并把“结构合法”与“有证据、选对实体、判断正确”分开。[方法章](docs/typed-values.md)沿具体字段解释摘录、计算和预测的区别；[三组实验题本](experiments/typed-values/README.md)提供原创输入、原生请求、编辑答案、对照和评分办法，分别研究缺失值、提取后的上下文损失、预测区间。

题本文件的 provider 状态保留 `NOT_RUN`，不因后续独立运行自动改写。`typed-values` 子命令可以准备请求、运行明确标注的 synthetic baseline／demo、导入本地响应，再回放字段、金额与区间评分。它与下面的 next-action 实验各用自己的结果契约；Clairic 与 api-lab 的真实采集走显式开启的有界 collector，日期协议与观察见[原生模型首轮实验](experiments/provider-pilot/README.md)。

## 研究升级

[首轮原生模型实验协议](experiments/provider-pilot/README.md)预先固定 Clef／Clef Flash 的主比较，以及 OpenRouter 上 Jev、Luna 和两条免费路线的参照，分开检验概率答案与表示稳定性、完整规则函数、Clairic 字段与下游任务。题本、重复、失败分母和预算在真实采集前固定；契约预检不充当模型质量结果。

[2026-10-23 实测](experiments/provider-pilot/README.md#实测结果)已完成 541 次有界原生调用。四个可用 Decisions 条件各完成 126 次正式尝试，Clairic 另完成 14 次；Luna／Mercury 被原隐私路由政策拦住，保留 missing。原始 16 函数两次重复：Clef 8/32、Flash 6/32、Jev 与 Mammoth 各 32/32 正确；Jev 在倒序与改写干预中仍有错误。三个世界的数值概率、菜单质量漂移、字段缺失和失败分别报告，不据这批固定合成案例声称普遍可靠。

[研究基础设施](docs/research-infrastructure.md)把数值事件概率和答案菜单效应分开，加入 perfect/uniform/wrong oracle、显式重复身份、planned set 与只读公共账本。四类 seed 生成器提供精确真值、source family 和固定 split；规则链可以从编译贯通穷举验证、最小反例、修复与版本过期检查。跨 run 比较保留失败分母，按 unit 汇总并按来源族估计区间；少簇只做描述。它们都是离线方法与 synthetic 控制，不能当作模型质量结论。

角色题本的专用 loss／guard 也保留到公共 ledger 与比较，不把合法语义错误和非法建议压成同一二元 loss。比较结果直接显示两侧来源，synthetic、imported、collector 和未知标记分别保留；自定义角色失败代价须与冻结矩阵一致。

[决策角色题本](experiments/decision-roles/README.md)新增证据选择、完整材料包、候选版本、控制权与 unknown effect 四类有限世界：16 个 world、三种等价表示、默认两次重复，共 96 requests。`research role-scenarios` 离线准备原生请求，`research role-report` 回放 retained collection，分别报告全分母正确率、固定 loss、非法建议和 guard 拒绝；确定性 policy 与模型看相同 body。首页 Samples 仍来自旧 next-action 题本，两个实验的标签和结果不混用。[Luna 补测](experiments/provider-pilot/luna-followup-2026-10-24.md)独立记录新采集，不改写首轮隐私失败。

2026-10-24 补测已完成 Luna 130 次请求：原始函数 2/32 完整正确，数值 MAE 0.0333333。独立角色实验目前完成 384/480 次：Jev 94/96、Luna 92/96、Mammoth 96/96 正确；Clef 42/48、Flash 33/48，另各有 48 planned missing，因采集环境凭据读取失败而未发送。角色题中的确定性 policy 为 96/96；模型没有优于该有限规则 baseline 的证据，guard 拒绝与正确建议分列。完整覆盖、反例及少量世界的解释边界见题本结果，不把部分采集当成同等覆盖的排名。

```bash
python3 -m decision_lab research generate --kind rules --seed 17 --units 20 --output runs/rule-worlds.json
python3 -m decision_lab research rule-workflow --dataset runs/rule-worlds.json --output runs/rule-repair.json
python3 -m decision_lab research rule-replay runs/rule-repair.json
```

`research collect` 复用保留的 api-lab 或 Clairic 请求，显式网络开关、凭据和三项预算缺一不可；串行执行，保留 raw bytes、失败耗时、取消和不确定发送，支持 checkpoint/resume。输入 token 估算不是输出或账单硬上限。真实调用需固定模型、输入和预算；实际发生的调用与失败由日期实验报告，不能从源码或 mock 推断。完整命令、恢复纪律、统计与后续方向见方法章。

`api-lab` 另支持 `clef`、`clef-flash` 与 `openrouter-decisions` 原生文本路线。CF 准备请求需要 `--account-id`，Body 短 selector 与 URL 模型 ID 分开；OpenRouter 使用原生 alpha Decisions endpoint，默认免费模型为 `baseten/mammoth-1:free`，可显式选其他免费或付费精确模型，不自动回退。原生 Score、分布均值与 confidence 分别保存。凭据环境变量和完整准备／采集命令见[API 实验说明](experiments/api-capabilities/README.md#新原生路线)与[采集方法](docs/research-infrastructure.md#有预算的采集与恢复)。

## 先做哪件事

| 你想做什么 | 从这里开始 |
| --- | --- |
| 理解整体目标与下一阶段研究 | [研究主线与能力边界](docs/research-programme.md) |
| 比较何时追问、问什么和最终损失 | [主动取证：完整多轮实验](experiments/active-evidence/README.md) |
| 研究 API 能力、准备原生多问题实验 | [能力方法](docs/api-capabilities.md) → [规则编译、概率组合、视觉判据](experiments/api-capabilities/README.md) |
| 查看最近 API、模型与价格变化 | [2026-10-20 Clairic 增量](research/2026-10-20/README.md)；[10-15 原生契约调查](research/2026-10-15/README.md) |
| 学会设计字段提取与预测实验 | [类型化输出](docs/typed-values.md) → [三组实验题本](experiments/typed-values/README.md) |
| 找一个有趣、可以动手的用法 | [20 种玩法与现成项目](docs/playbook.md) |
| 理解这个领域和证据边界 | [2026-10-08 调查及复算](research/2026-10-08/README.md) |
| 找 SDK、开放模型、运行时或评测项目 | [按问题分组的项目地图](docs/projects.md) |
| 运行离线判断或取值实验 | [next-action 实验](experiments/next-action/README.md)；[typed-values CLI](experiments/typed-values/README.md) |
| 决定怎样接入自己的工作流 | [接入设计](docs/integration.md) |
| 更新快速变化的资料 | [维护方法](docs/maintenance.md) |

## 五分钟跑通离线实验

需要 Python 3.11+，核心 CLI 无第三方依赖。在仓库根目录运行：

```bash
python3 -m decision_lab api-lab list
python3 -m decision_lab api-lab validate
python3 -m decision_lab api-lab prepare --experiment rule-compile --route decisions --limit 1
python3 tools/catalog.py capabilities --query probability --json
```

新实验的 demo、响应导入、回放和比较命令见[实验说明](experiments/api-capabilities/README.md)。它们不读取凭据、不发送请求；图片 criteria 只为 Jev 准备原生 assets 与所需的非秘密 header。字段答案、原生选项概率和 confidence 分开保存，外部导入不被标成项目 live 采集。模型原始结果与独立评分保存在新的运行目录，旧 next-action 与 typed-values 记录保持各自的契约。

原有 next-action 实验继续使用相同入口：

```bash
python3 -m decision_lab validate experiments/next-action/cases.json
python3 -m decision_lab baseline-run experiments/next-action/cases.json --run-dir runs/baseline-001
python3 -m decision_lab demo experiments/next-action/cases.json --run-dir runs/demo-001
python3 -m decision_lab replay runs/demo-001 experiments/next-action/cases.json
```

任务是：给定文档/变更和一个主张，推荐下一步核对动作。25 个原创合成用例覆盖中文、英文与混写；同一来源的变体保持在同一个 dev/test 分组。baseline 使用确定性规则；demo 有意构造一个错误和一个 unknown。**这些都不是模型实测，也不构成质量排名。** 每次使用新运行目录，以保留旧记录。

同一个入口下，类型化取值使用独立子命令：

```bash
python3 -m decision_lab typed-values validate
python3 -m decision_lab typed-values prepare --case-id source-missing
python3 -m decision_lab typed-values baseline-run --run-dir runs/typed-baseline-001
python3 -m decision_lab typed-values demo --run-dir runs/typed-demo-001
python3 -m decision_lab typed-values replay runs/typed-demo-001
```

`prepare` 仅打印请求；baseline 和 demo 均为 synthetic。已有本地响应可用 `typed-values import --responses <responses.json> --run-dir <新目录>` 导入，再由 `replay` 重算评分。导入格式、三条判断路径和 span 约定见 [typed-values 实验说明](experiments/typed-values/README.md)。以上命令不读取凭据、不请求 provider，运行结果不会改写题本的 `NOT_RUN` 状态。

```bash
# 检查两条原生 API 的请求，不发送
python3 -m decision_lab prepare experiments/next-action/cases.json --route jev --limit 1
python3 -m decision_lab prepare experiments/next-action/cases.json --route decisions --limit 1

# 离线查询调查记录
python3 tools/catalog.py projects --query calibration
python3 tools/catalog.py models --query clef --json
python3 tools/catalog.py updates --query clairic
python3 tools/catalog.py updates --date 2026-10-15 --query jev
python3 tools/catalog.py updates --date 2026-10-20 --query clairic
python3 tools/catalog.py capabilities --query criteria --json
python3 tools/catalog.py recipes --query NPC --json
```

这套 next-action 的旧 live collector 支持 TypeSafe Jev 与 OpenAI Decisions 原生 HTTP 形状；需要操作者主动选择网络调用、配置环境变量凭据并给出调用上限。具体命令与限制见[实验说明](experiments/next-action/README.md)。next-action 尚无独立 live 结果，不能用另一套 [api-lab／Clairic 的日期实验](experiments/provider-pilot/README.md)冒充它的证据；没有生产接入。

## 阅读站与验证

阅读站从同一份 Markdown 和 catalog 构建。首页以全幅排版和原创 WebGL 粒子作品开场：在编织、分岔、环流三种形态间连续变形，鼠标移动会改变整体姿态，拖拽旋转后带有惯性，轻点可以冲散；方向键可调整视角，Home 或复位按钮恢复当前形态的初始视角。巨幅标题的字母可以被鼠标拨动、拖开，松手后弹回原位并带出切片残影。下滑按「玩法 → 实验 → 工具与阅读」探索：20 种玩法支持分类与关键词筛选，以像素卡带切换当前配方并更新可分享的 fragment；原创低分辨率信号场显示由同一 catalog 生成的线路，旁边明确提示方形节点可直接点按。已有选项走前向分支，补材料／交人工走回环，unknown 独立成 × 出口与无动作编号的按钮；文字、画布和结果读数同步。结果区分别展示 ok、unknown、refusal、error：手动试选产生前两类预览，API 拒答与调用失败可用明确标注的离线示例查看，它们会取消全部选项。清除试选可回到未作答。结果同时区分 choice 与 probabilities / confidence；浏览器不请求模型，不捏造概率。这里只演示 Choice profile；输出 primitive 和记录状态的区别见[结果契约](docs/method.md#结果状态与输出类型)。可以展开第一步、机制和失败方式，复制不绑定 provider 的任务 JSON，再沿完整配方进入 API 示例。两项已有离线实验，其余为待接入验证的提案。五组分类还可探索历史 catalog 中的 21 个项目。

概率地形可以切换示意分布、调整候选偏向，并查看 maxP 和熵；历史像素矩阵可切换三组任务及高 maxP 子集，显示对应正确／错误数量；切换时格子以有限的阶梯动效落位，数字立即更新。三个原创合成案例允许选择下一步动作、查看编辑标签和理由。粒子几何与颜色只用于视觉反馈，不编码模型关系或性能；概率地形也不是模型输出。PLAY 点阵招牌轮播六组玩法记号，每屏最多两组；入口图标、概率地形和历史矩阵带有受控动效。Space Grotesk 用于英文 display 排版，Silkscreen 用于少量标签，均自托管。长文支持章节目录、阅读进度、代码复制和表格内横向滚动；项目地图可检索并跳到匹配行，原有局限和来源说明始终保留。

浏览器不请求模型，不向外部字体服务、分析脚本或 CDN 发请求，不保存练习答案；仅在本地保存手动选择的日／夜外观。默认外观跟随系统，所有阅读页共用同一选择。动态作品可暂停，并尊重系统减少动态效果偏好；页面后台或作品滚出视野时停止动画。暂停或减少动态效果时仍可切换静态形态、拖动或用键盘调整静态视角；鼠标悬停不会唤起动画。标题动效随封面暂停，下方共享暂停按钮同时控制信号场、招牌、图标、概率地形和历史矩阵等环境动态；暂停时仍可点选静态路线、查看离线状态或调整示意分布，读数立即更新。减少动态效果时不播放这些动画。WebGL 或 Canvas 2D 不可用时保留对应静态图；关闭 JavaScript 后仍可阅读全部玩法、历史汇总、正文与案例材料。构建需要 Python 3.11+ 与 `requirements-site.txt`；完整验证另外需要 Node.js 22+，无需安装 npm packages。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-site.txt
.venv/bin/python tools/check.py
.venv/bin/python tools/build_site.py
python3 -m http.server 8765 --bind 127.0.0.1 --directory _site
```

打开 `http://127.0.0.1:8765`。`_site/` 是派生输出；构建器只发布显式列出的正文、公共研究文件与站点资源。只验证核心 CLI 和数据时，可用标准库执行 `python3 tools/check.py --core-only`。CI 的唯一入口也是 `tools/check.py`。

## 证据与限制

[2026-10-22 能力核查](research/2026-10-22/README.md)记录 16 项来源、8 条变化，并为旧 12 probes 保留新的日期版本。OpenAI reference 的 400 题与固定 Python SDK 说明的 200 题差异仍待服务端验证；Jev 图像标准处于实验状态。语义特征、语义寻址、Clairic list/forecast、时间与音视频是已写明对照的研究设计，尚无这些完整实验的采集结果。历史快照计数不会因新增能力卡片而自动刷新。

首期调查包含 23 个模型/服务实体、21 个相关仓库、6 项研究、171 条来源索引。我们复算了随包历史输入：1,000 个案例、4,000 条概率记录，14 项作者汇总核对一致。原始预测记录不随仓库分发；有原始 evidence bundle 的读者可以按[复算说明](research/2026-10-08/README.md)检查。

[2026-10-15 增量](research/2026-10-15/README.md)另存 30 条来源、12 条变化记录，覆盖 Jev 1.14、OpenAI Decisions 契约与 SDK 差异、Cloudflare、Fastino、Upstage。它没有覆盖全部首期条目，也没有重写历史快照；玩法中每项项目证据另标截点。公开文档和标价不等于实际调用、账单或质量验证。

[2026-10-20 增量](research/2026-10-20/README.md)追加 8 项官方来源、7 项变化记录，核查 Clairic 字段契约与 Cloudflare 标价。文档 schema 和官方示例固定到源码 revision；预测区间、中文位置映射及长输入边界等待实验。模型列表仍是 10-08 历史 census，新实体先进入有日期的变化索引，不静默改写历史数量。

这些是特定任务与历史版本的证据。选项集合、语言、上下文截断、问题依赖和 confidence 定义都会改变解释。高 maxP 不能替代针对实际任务的校准；unknown、API refusal 和错误也不能混记成“否”。[评估方法](docs/method.md)说明如何读结果。

## 数据边界与许可

公共内容使用公开来源或原创合成任务。原始 chat、私人项目上下文、凭据与真实运行记录不进入 Git。collector 会把选择的任务输入发送给对应 provider；运行记录保留任务关联和原始响应，真实输入的记录应按输入的敏感程度保管。模型建议不会自动执行，不写入个人记忆或修改项目。

原创代码：[SUL-1.0](LICENSE)。原创文档、图示与合成案例：[CC BY-NC-SA 4.0](LICENSE-DOCUMENTATION.md)。第三方模型、数据和引用材料保留其自身条款；详细范围与归属见 [LICENSING.md](LICENSING.md)。这不是 OSI open-source 许可声明。
