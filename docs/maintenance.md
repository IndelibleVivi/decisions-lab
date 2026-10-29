# 快速变化的信息，怎样持续维护

让变化发生在它所属的表面。可复现性依赖当时的事实留得住；实用性依赖新的事实找得到。

## 三层时间

| 层 | 内容 | 更新方式 |
| --- | --- | --- |
| 方法 | 任务设计、证据分级、校准、接入边界 | 出现改变判断的新证据时修订 |
| 日期快照 | 来源、模型/路线、版本、价格、作者报告 | 新调查放入新的日期目录；历史勘误明确标注 |
| 实验记录 | 输入、profile、模型、输出、用量、错误 | 每次写新目录；原始结果不覆写为新结果 |

`research/2026-10-08/` 是首期快照，`catalog/index.json` 分别声明 `source_root`、`update_history` 和 `latest_update`。最新增量目前为 `research/2026-10-22/updates.json`；10-15、10-20 记录继续可读、可查询。每轮用变化记录关联来源 ID，保留核查日期、访问结果、未覆盖范围和 live 状态。新增定向增量不重写首期 census，也不代表所有链接已重新检查。`docs/current-state.md` 只描述本项目目前做到了哪里，不承担整份领域百科。

```bash
python3 tools/catalog.py updates --query clairic
python3 tools/catalog.py updates --date 2026-10-15 --query jev --json
python3 tools/catalog.py capabilities --query criteria --json
```

`models/projects/sources` 仍查询首期快照；`updates` 默认仅查最新增量，`--date` 可选择已登记的历史日期。不要把旧 Jev 记录因新一轮发布而改写成今天复核。新增调查时登记 `update_history`、切换 `latest_update`，并给 builder 的正文／资产 allowlist 添加新文件；首页更新入口和标题从同一索引读取。

## 按变化的后果重查

- 准备调用某条路线前：重查 endpoint、认证、请求/响应 shape、模型标识和输入限制。
- 准备估算预算前：记录价格页日期、计费单位、共享 state/缓存/长上下文规则。估算与实际 usage/bill 分开。
- 准备采用开源或 source-available 项目前：核查确切 revision、license、依赖、运行要求和维护状况。
- 发现来源失效或相互矛盾：保留原先引用和截点，添加勘误或新来源，说明哪个结论改变了。

本仓库没有自动监控、定时刷新或后台网络任务。以后若启用监控，优先通知会影响现有使用路径的变化；文档页面改动本身不自动触发模型实验或项目改写。

## 更新 catalog 与阅读站

```bash
python3 tools/catalog.py render
python3 tools/check.py --core-only
# 安装 requirements-site.txt 并准备 Node.js 22+ 后：
python3 tools/check.py
python3 tools/build_site.py
```

`docs/projects.md` 是生成投影：分组和面向读者的中文边界摘要编辑 `catalog/index.json`，事实来自相应日期的结构化来源。阅读站 `_site/` 只由 builder 生成；不要同时维护 Markdown 和 HTML 两套正文。英文 README 保持能力、命令、边界与中文版一致，其余详细正文当前以中文为准。

玩法卡片编辑 `catalog/recipes.json`，详细解释与操作路径编辑 `docs/playbook.md`。稳定 ID 同时用于 Markdown 标题、站点 fragment 和测试映射；修改标题不应破坏 ID。项目机制、核查日期、原创提案与已实现离线实验必须分别表述。首页复制的是通用任务定义，不是可直接发送给任意 provider 的请求体；原生请求以带日期的 API 示例及实验 adapter 为准。新增来源更新各自的截点，不把文档编辑日期当成全部链接的复核日期。

类型化取值的解释由 `docs/typed-values.md` 拥有；三组题本和原创请求在 `experiments/typed-values/`。`examples.json` 的编辑答案、干预和观测结果与 provider 输出分开保存，状态为 NOT_RUN。`decision_lab typed-values` 使用独立的离线记录和评分契约；不改 Choice 的 action/probabilities，也不改变配方卡片的已实现数量。修改题本或评分时，同时验证请求不含编辑答案／事后观测、null 不补 guess、三路径的作答正确性与任务完成率分列、区间覆盖与宽度分列。显式 collector 已实现，真实采集仍需满足单独的模型/输入授权、网络、凭据和预算约束，见[研究基础设施](research-infrastructure.md)。

API 能力方向编辑 `catalog/capabilities.json` 和 `docs/api-capabilities.md`，来源 ID 解析到索引指定的日期增量。`api-lab` 的三组题本与运行说明在 `experiments/api-capabilities/`，不增加玩法卡片的已实现数量。新日期的 12 probes 保留历史 source ID 的原来源日期，并修订已失效的接口前提；设计状态不能因某个新题本实现而改为已实测。修改生成器、原生请求或评分时，检查 ground truth 隔离、分题 refusal/error、完整 request 快照、缺失/部分导入 coverage、概率对象语义以及最小反例。推理记录和评价分开核对，不能由当前 adapter 的变化抹去历史请求。

持续研究目标由 `docs/research-programme.md` 拥有；主动取证设计与可执行契约由 `decision_lab/evidence.py`、`evidence_workflow.py` 和 `experiments/active-evidence/README.md` 拥有。修改 query、先验、损失或预算即改变任务；验证相同可见历史不泄漏 actual world、一步／多步 oracle 区别、回合绑定、已花成本与 missing 分母、prior/scenario/family 汇总及业务暂缓与 API failure。回合继续用 api-lab/collector，不能将整个 manifest 当 provider body 或新增隐藏网络。保存新的 state 文件，不能覆盖旧回合或从缓存评价恢复事实。

E3 的 stage 关联、三路径与阶段干预由 `decision_lab/typed_dag.py` 和 `experiments/typed-dag/README.md` 拥有，原生 records/parsers/transport 仍复用现有 owner。修改抽取字段、计算或检索时，核查上一阶段实际值是否进入下一阶段 body、schema 不充分配对是否仍不可由字段区分、null 是否保持缺失、gold-derived 来源与完整分母是否保留。共享上游请求只能计账一次，保存重载须重新解码来源并拒绝过期阶段。日期 E2 实测由自己的协议页记录，不能倒写 authoring 状态或把有限 planning 结论扩成开放调查。

更换站点资产后，旧 `_site/` 可能留下已退役的文件；builder 会报 `Unexpected existing output`，不会擅自清空目录。先检查报错路径，确认它仅是旧的生成文件，再移除该文件并重新构建。当前源码不再生成旧版的 `site/orbit.js`。

历史矩阵的三组数字来自 `research/2026-10-08/reanalysis/sys1_reanalysis.json`；交互练习选取 `experiments/next-action/cases.json` 中的三个 dev cases，标签与理由随构建投影。矩阵每格代表一条记录的计数，按汇总结果分组，不声称恢复原始样本身份或顺序。修改这些源时同时检查首页显示；不要在 HTML 或浏览器脚本里另写答案副本。站点脚本变更会生成新的资源版本 URL，供浏览器区分构建后的缓存。完整验证包含无网络 JavaScript 行为检查；排版、手机断行和实际点击仍需浏览器检视。

## 本地研究台的维护边界

`site/studio.html` 是首页实验 D 的片段，由同一 builder 插入；只维护这一入口。`studio.js/css` 使用现有字体、颜色、像素卡带与实验区，不生成独立欢迎页。静态 build 中的 session token 为空，不请求研究 API；本地 `studio_server` 构建并服务相同 allowlist，只向本机首页注入会话 token。新增页面必须进入 `PAGES`；研究包、源码解释器与 runs 永远不进入 allowlist。

修改会话行为时检查冻结/派生、revision 冲突、失败原子性、完整 planned 分母、错误条件导入、原生 provenance 和分析绑定。历史源码只来自本机 snapshot registry；导入包不能安装程序，缺少旧源码或 Python runtime 不匹配时应明确拒绝历史复现，当前重分析仍可另存结果。命令与当前边界同步 [Studio 操作说明](studio.md)、中英文 README 和仓库契约。

## 图形与外观的维护边界

`site/sculpture.js` 的 WebGL 粒子作品在编织、分岔、环流间变形，支持整体姿态跟随、带惯性的拖拽、衰减轨迹、冲散和键盘旋转；Home／复位会清除视角偏移、惯性和冲散，保持当前选定形态。暂停／减少动态效果下，拖拽与键盘仅更新静帧，悬停不启动动画；触摸保留纵向滚动。取消、失焦、离屏、后台或 context 丢失会清理拖拽和 pointer capture。几何和颜色不代表模型关系或性能。无 WebGL 或 context 丢失时保留 SVG，恢复 context 后重新初始化并保留暂停状态。

`site/lettering.js` 在现有标题内渐进拆分字母，鼠标邻近／拖拽改变位移与倾角，松手有限回弹；语义 H1 不变，不另存文字。它与封面暂停状态联动，减少动态、失焦、后台或离屏时清理动画，窗口变化后重新测量字母位置。

`site/atlas.js` 渐进增强独立的项目分类切换，项目名称、分组和链接由构建器读取 catalog 与带日期的 repositories 快照生成；不另存事实副本。无 JavaScript 时保留首组入口和完整项目目录链接。

`site/recipes.js` 增强玩法分类、关键词搜索、索引选择、fragment 导航和复制；默认进入「创作与互动」，选「全部」可检索二十项，切换分类会保留仍匹配的当前项。手动选择卡带更新 URL fragment；静态配方与所有选项来自同份 catalog。`tools/build_site.py` 的 `option_kind()` 负责 UI 分类元数据：显式 unknown、请求材料／人工、普通业务选项；「直接拒绝」「都不适用」「无法从分布确定」等业务答案不自动归成 API refusal、unknown 或补上下文。unknown 在 HTML 独立区域显示 UNK，仍完整保留在复制的任务定义里。

`recipes.js` 是手动试选／离线示例的状态 owner，更新 `.choice-machine` 的 `data-outcome` / `data-preview-mode`、按钮、SVG 路线和结果读数；`site/pixels.js` 消费同一状态绘制 320×180 信号场。ok 的普通分支与补上下文回环保留动作编号，unknown 使用独立 × 分支；refusal/error 只由明确标注的离线示例触发，取消全部选项，画布不显示可采用动作。清除回到未试选。画布节点点击回到 HTML 按钮路径；示例不改任务 JSON，不生成概率／confidence，不发网络请求。原生输出类型和归一化状态的边界见[结果契约](method.md#结果状态与输出类型)。无 JavaScript 时全部配方仍可展开阅读；无 Canvas 2D 时保留 SVG、文字按钮及结果区。

`pixels.js` 拥有下方共享暂停状态，通过 document `pixelmotionchange` 同步消费者；无 Canvas 2D 仍提供共享暂停。`site/motion.js` 管滚动入场、PLAY 招牌轮播和图标信号活化：招牌每屏最多两组记号，所有绘制留在画布内。信号场一个 RAF owner 只更新当前可见画布；招牌／图标按自身可见性绘制，暂停、减少动态和后台停止。CSS 装饰同步共享状态和可见性；暂停时入场内容保持可读。`site/fonts/` 自托管第三方 Space Grotesk 与 Silkscreen，完整 copyright notice 和 OFL 条款随构建分发，不请求外部字体服务。

`site/field.js` 的三个高斯山峰由示意候选概率加权，maxP 和 Shannon entropy 使用同一分布计算；权重缓动与指针变形只改画面，不改文本读数。共享暂停／减少动态下控件立即更新静态地形；几何投影不等于概率校准。`site/evidence.js` 只投影构建时传入的历史汇总，切换高 maxP 时保留完整格子位置并淡化筛选外记录。切换时，有限阶梯动画只改变格子的视觉位置；数字和类别立即同步。快速切换、减少动态、离屏、后台或像素暂停会取消旧动画。作品／示意／历史标签需要一起保留。

`site/theme.js` 在样式加载前读取本地外观选择，未选择时跟随系统；只写入 `decisions-theme`，不储存输入或练习答案。接入说明的原创 `site/flow.svg` 在构建时内联，随同一主题变色；原 SVG 仍是唯一编辑源。各个持续播放的 Canvas 都提供暂停，遵循减少动态效果偏好，并在后台／视野外停止。无 JavaScript 时保留内嵌 SVG 和静态汇总。

视觉研究参考了 [TypeSafe Jev](https://typesafe.ai/) 的点阵语汇、[tixy](https://tixy.land/) 的参数驱动画面，以及 [Seeing Theory](https://seeing-theory.brown.edu/) 把概率概念做成可操作对象的方式。本项目图形与交互独立实现，未复制上述项目的代码或素材；参考不构成对模型效果的背书。

改动图形时同时看日间、夜间、桌面、手机、静止和运动状态；自动化行为检查不能替代视觉检查。首屏高度、下滑入口、长文阅读和控件反馈应在同一次浏览器检查中连起来使用。

## 新结果要回答什么

记录本次要改变的决策、输入如何选择、分组/切分、baseline、具体路线和模型、未通过案例、原始概率、计时/费用的来源，以及结果不能说明什么。没有 live 运行就写未运行；局部失败也保留。研究贡献可以是复算、反例或修正一个错误解释，不必每次都是排行榜。

维护代码与内容时运行统一入口。GitHub Actions 只负责同一入口的无凭据验证，不运行模型、不发布站点。公开前检查原始导出、私人记录、路径、凭据和第三方许可范围。

交互设计参考了 [anatomy](https://github.com/wheresryan22/anatomy) 的部件／读数同步与直接操控、[Interactive Particles](https://tympanus.net/codrops/2019/01/17/interactive-particles-with-three-js/) 的轨迹衰减机制，以及 [LOOPY](https://ncase.me/loopy/) 的动作与后果就地呈现。本站使用原生 WebGL、Canvas 2D 与 SVG，几何和状态逻辑由本项目独立实现，没有引入这些项目的代码、素材或依赖。
