# Decisions Lab · 仓库契约

这是决策模型的研究、契约比较与可复现实验项目。中文是正文主语言，标识符与接口字段保留原文。

## 真源与边界

- `README.md` / `README.en.md` 管读者入口、已支持能力、命令与限制；`docs/` 管解释、维护方法和当前状态。
- `research/2026-10-08/` 拥有首期调查快照；`research/2026-10-15/`、`research/2026-10-20/`、`research/2026-10-22/` 分别拥有各自定向增量正文和 `updates.json`。10-22 的 `public_probe_protocol.json` 是旧 12 probes 的新日期设计，历史版不变、两版均 NOT_RUN。`catalog/index.json` 的 `update_history` 保留可查询日期，`latest_update` 指向最新一轮。增量只覆盖其中列出的来源，不刷新全量 census。历史事实不能在构建时自动刷新；勘误单独说明。
- `catalog/` 拥有模型、服务路线、相关项目与来源的结构化索引；`index.json` 分别声明历史快照和最新增量。`recipes.json` 拥有玩法卡片事实、来源日期与实现状态；`docs/playbook.md` 拥有解释及用法，二者的稳定 recipe ID 必须对应。官方文档、原作者报告、历史数据复算与本项目实测是不同证据。
- `decision_lab/` 拥有实验 CLI；`experiments/next-action/` 拥有原创合成任务、标签和实验说明；`tests/` 提供相应行为证据。
- `decision_lab/role_tasks.py` 与 `experiments/decision-roles/README.md` 拥有独立角色题本、有限 oracle、只看 body 的 policy、hard-state guard、retained loss 和完整 planned 分母报告；`research role-scenarios/role-report` 复用原生 api-lab 与 collector，不新增 transport。16 worlds 的表示／repeats 相关，业务 none 与 API unknown/refusal/error/missing 分开；guard 拒绝不等于模型答对。首页 Samples 仍取旧 next-action 三例，不转移 live 结果。日期协议只公开合成设计与汇总，私人项目 source mapping 不进入公共题本。
- 角色专用报告与 `ledger.from_api` 必须共用 `role_tasks.evaluate_request`，保留 `role_workflow_loss`、完整 loss matrix、`retained_failure_loss`、unsafe／guard／动作语义；非 ok 的 ledger correctness 保持 null。比较不可用通用二元错误覆盖专用 loss 或静默改变 retained failure 代价。通用与 episode 比较结果都保留两侧来源标记，unknown synthetic 保持 null；来源声明不等于 live 认证。
- `docs/research-programme.md` 拥有持续研究目标、能力关系和阶段门槛；`decision_lab/evidence.py` 与 `experiments/active-evidence/README.md` 拥有有限主动取证环境、已知假设表、预算、一步／多步 oracle 和终局损失。`evidence_workflow.py` 只将可见状态接到既有 api-lab/collector 原生回合；actual world、未揭示的实际观察与本地评分不能进入 body，整 manifest 不得发送。回合原子 apply，missing/uncertain 保留待处理，业务 abstain 与 API failure 分开；digest 仅校验一致性。等 world 行均值、prior 加权及 family 等权分开，任意模型轨迹不伪造完整 policy expected regret。默认无网络，query 只揭示本地合成观察；全程预算、真实模型实验与生产采用均须独立证据。
- `experiments/active-evidence/pilot-2026-10-28.md` 拥有 E2 首轮三模型有限规划的事前设计、授权上限和公开汇总；原始轨迹、账户 observation 和本机 operator 不进入 Git／站点。完整假设表与精确后验属于可见契约，不能将本实验解释为开放调查或等 provider calls 比较。
- `experiments/provider-pilot/README.md` 拥有首轮原生 provider 比较的事前研究问题、固定模型、题本选择、重复、失败分母、预算和停止规则；预检、真实采集及汇总状态分别报告。运行 manifest、原始响应、账户用量和凭据留在本机，不因公开实验协议进入 Git 或站点。
- `catalog/capabilities.json` 拥有 7 个 API 能力方向的来源关联、假设、对照和本地覆盖；`docs/api-capabilities.md` 拥有研究方法，`experiments/api-capabilities/` 与 `decision_lab` 的 `api-lab` 子命令拥有规则编译、概率组合、视觉 criteria 的独立离线题本和记录／评分路径。多问题保留每题原语与结果，不绑定 next-action 常量；旧 Choice 和 typed-values 契约保留其当前调用者。题本真值不进入请求，事件概率／数值答案／选项分布／confidence 分开；Jev 图片用原生 assets 引用及实验 header，不能用 OpenAI 图像输入冒充同构 criteria。synthetic、imported 和 live 证据分开；历史题本保留 NOT_RUN authoring 状态，日期实验与真实 run 独立报告。网络仅走显式开启的有界 collector，不暗中启用。
- `docs/typed-values.md` 拥有类型化输出的方法；`experiments/typed-values/` 拥有三组实验题本和原创 `examples.json`，题本保留 NOT_RUN authoring 状态，后续真实运行不写回旧快照。`decision_lab` 的 `typed-values` 子命令拥有独立的离线请求准备、synthetic 演示／baseline、响应导入和评分回放，不复用 Choice action/probabilities 契约。原生 scalar null 不补 guess，不推断为 unknown/refusal；未核定的 span 约定明确报告。编辑答案与事后观测不能进入模型请求；离线导入不证明项目曾做 live 采集。
- `decision_lab/typed_dag.py` 与 `experiments/typed-dag/README.md` 拥有 E3 串行抽取／Decimal／decision 的任务、stage binding、三路径与 gold-stage 干预。原生 parser、record 和 transport 仍由 typed-values／api-lab／collector 拥有；后续 body 必须依赖实际上一阶段响应，gold-derived 与 synthetic 来源显式保留。null 不补 guess，字段真值不能进入提取请求，schema 不充分不能归因抽取错；完整 planned 终局分母和每原生 request 一次 accounting 不因下游复用而丢失或倍增。
- `experiments/typed-dag/pilot-2026-10-30.md` 拥有 E3 首轮 Clairic＋官方 Luna 八条件实测设计与汇总。普通 quote 未通过前缀校验、严格 body policy agreement 与语义充分性、等值 Decimal 格式变化与算术效果分别解释；不倒写原始记录或把 gold-derived 条件当完整 live 工作流。原始轨迹、冻结源码、operator 与账户计量留在本机。
- `decision_lab/collection.py` 拥有 api-lab／Clairic retained plan 的有界串行采集、attempt/checkpoint/resume；api-lab 支持 decisions/jev/clef/clef-flash/openrouter-decisions，CF 的 Body selector 与 URL 模型 ID 分开，账号固定在 retained endpoint；默认无网络，真实调用仍需明确模型、输入、凭据与预算。`ledger.py` 只读投影三类原生记录，`comparison.py` 拥有配对、失败分母、unit聚合、source-family区间与calibration/test隔离；正常但无已定义loss的estimate不伪造二元评分。`generators.py` 拥有四类seed有限世界、oracle、变换和分组；`rule_workflow.py` 拥有有限规则的穷举验证／反例修复／版本探针。公共方法入口是 `docs/research-infrastructure.md`，详细契约在 `experiments/generated/` 与 `experiments/comparison/`。原始bytes、真实记录与生成题本只保存在 Git 外或明确忽略的本机 runs，不提交或进入站点。
- `decision_lab/studio.py` 拥有本机研究会话、冻结设计、追加证据/分析和笔记、原子保存与 revision；`interpretation.py` 复用各原生 evaluator，历史解释器仅由本机源码快照产生，导入 JSON 不安装/执行代码。`studio_server.py` 仅绑定 loopback，使用 Host/Origin/session token 和站点 allowlist；无 provider transport。`site/studio.html` 是原首页实验 D 的构建片段，`studio.js/css` 只增强该区域，不建立第二套前端；静态站无 session token 时不连接 API。`docs/studio.md` 拥有操作与隐私边界。研究记录与解释器保留在忽略的 runs 或仓库外，不能进入站点/Git。
- `measurement.py` 拥有科学任务投影、measurement 与 selection signal；显式 pairing 必须重新核对保留 native manifest、逐题映射与测量单位，不能仅凭自行声明的 ID 绕过任务不一致。numeric absolute error 与角色专用 loss 不压成二元错；不同 signal 不共用阈值。
- `tools/` 拥有内容投影与统一检查入口；构建输出和真实运行记录不提交。正文和 catalog 是编辑源，生成页不另行维护。
- `site/` 拥有阅读站样式与渐进交互；`tools/build_site.py` 的显式 allowlist 决定站点内容。首页 WebGL 粒子作品不编码事实，无 WebGL 时保留 SVG；`lettering.js` 只增强原语义 H1 的有限位移与回弹。`atlas.js` 只切换 catalog／repositories 快照生成的分类入口。`theme.js` 仅保存外观偏好。
- `recipes.js` 拥有玩法筛选、单配方选择、稳定 fragment、手动试选／离线结果示例和 provider-neutral 任务复制；`build_site.py` 的 `option_kind()` 拥有 UI 分类元数据。unknown 独立显示为 UNK／×，仍保留在请求选项里；补材料／交人工为正常 ok 选项，业务文案的「拒绝」「不适用」不等于 API refusal 或 unknown。`.choice-machine` 的 outcome／previewMode 同步 HTML、SVG 和 `pixels.js` 信号场；refusal/error 示例明确标注离线、取消全部选项，不能假装有可采用动作或真实调用。默认未试选；不生成概率／confidence、不改任务 JSON。当前只演示 Choice profile，归一化状态与原生输出类型分别说明。
- `pixels.js` 拥有下方共享暂停，通过 document `pixelmotionchange` 同步消费者；无 Canvas 2D 仍保留 SVG、HTML 交互与共享暂停。`motion.js` 管滚动入场、PLAY 招牌轮播（每屏最多两组记号）与图标活化；`field.js` 的权重插值／指针变形只影响示意画面，不改即时概率读数；`evidence.js` 的扫描／有限落位只影响装饰，不改复算计数；`lab.js` 的练习与标签来自既有 dev cases。动态尊重减少动态效果、暂停、前后台和可见性；静态操作仍即时反馈。`site/fonts/` 自托管 Space Grotesk 与 Silkscreen（OFL-1.1），版权 notice 与许可随构建分发。`docs/projects.md` 由 catalog 生成，`_site/` 是忽略的构建输出。
- 原始 chat、私人采用记录、账号、凭据、个人路径与 continuity 不进入仓库。公共实例只使用公开或原创合成输入。
- 模型判断是建议；实验不执行其建议，不变更外部系统。unknown、refusal、调用失败与正常答案分别记录。
- 离线演示、fixture 验证、HTTP 模拟与真实 provider 调用分别报告。没有真实运行证据，不宣称 API 可用、模型质量、实际价格或生产效果。
- live 调用需操作者明确选择、凭据和调用上限；默认命令离线。测试和 CI 不使用真实凭据、不调用模型。
- 许可条款由 owner 选择；第三方材料保留原有条款和归属，不能被项目默认许可覆盖。选定后以 `LICENSING.md` 为准。

## 协作与验证

允许多个责任面并行，但一个文件只有一个 writer。临时 worker 只处理工单指定路径，不读取私人连续性或主会话说明，不调用 Oracle、不再派工，不改全局 routing，不 commit/push/发布/部署或操作账号。

本项目统一验证入口由 `python3 tools/check.py` 提供，完整检查先安装 `requirements-site.txt` 并准备 Node.js 22+；浏览器逻辑测试不需要 npm packages。仅核心 CLI/数据检查使用 `--core-only`。provider CI 只调用此入口，不运行模型或部署。源码支持 Python 3.11+；优先标准库，只有当前功能需要时才添加依赖。静态检查不证明视觉质量；修改站点布局/交互时另做桌面与手机的真实浏览器检查。

修改 CLI、记录格式、失败行为时，更新对应实验说明和 README，并验证真实入口；内容改动检查相对链接、来源映射、日期与事实投影。报告 source、测试、live 推理和公开状态时分开。
