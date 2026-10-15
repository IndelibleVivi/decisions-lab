# Decisions Lab · 仓库契约

这是决策模型的研究、契约比较与可复现实验项目。中文是正文主语言，标识符与接口字段保留原文。

## 真源与边界

- `README.md` / `README.en.md` 管读者入口、已支持能力、命令与限制；`docs/` 管解释、维护方法和当前状态。
- `research/2026-10-08/` 拥有首期调查快照；`research/2026-10-15/` 拥有定向增量正文和 `updates.json`。增量只覆盖其中列出的来源，不刷新全量 census。历史事实不能在构建时自动刷新；勘误单独说明。
- `catalog/` 拥有模型、服务路线、相关项目与来源的结构化索引；`index.json` 分别声明历史快照和最新增量。`recipes.json` 拥有玩法卡片事实、来源日期与实现状态；`docs/playbook.md` 拥有解释及用法，二者的稳定 recipe ID 必须对应。官方文档、原作者报告、历史数据复算与本项目实测是不同证据。
- `decision_lab/` 拥有实验 CLI；`experiments/next-action/` 拥有原创合成任务、标签和实验说明；`tests/` 提供相应行为证据。
- `tools/` 拥有内容投影与统一检查入口；构建输出和真实运行记录不提交。正文和 catalog 是编辑源，生成页不另行维护。
- `site/` 拥有阅读站昼夜样式、渐进搜索、目录/复制交互、合成案例练习与原创图示；`tools/build_site.py` 的显式 allowlist 决定站点内容。首页 WebGL 粒子作品不编码事实，无 WebGL 时保留 SVG；`lettering.js` 只增强原有标题的有限位移与回弹，保留语义 H1；`recipes.js` 负责 catalog 投影的筛选、单配方选择、稳定 fragment、手动分支预览和 provider-neutral 任务复制；分流图的路线与候选同源；`pixels.js` 读取当前候选绘制原创像素信号机，画布出口回到 HTML 选项路径，无 Canvas 2D 时保留 SVG。手动预览不修改任务定义、不生成概率、不请求模型。分类入口由 catalog 分组及 repositories 快照生成，`atlas.js` 只切换展示；概率地形仅为数学示意。历史像素矩阵数字来自复算 JSON，练习来自既有 dev cases；不另存事实副本。`theme.js` 仅保存外观偏好，动画尊重减少动态效果、暂停及前后台状态。`docs/projects.md` 由 catalog 生成，`_site/` 是忽略的构建输出。
- 原始 chat、私人采用记录、账号、凭据、个人路径与 continuity 不进入仓库。公共实例只使用公开或原创合成输入。
- 模型判断是建议；实验不执行其建议，不变更外部系统。unknown、refusal、调用失败与正常答案分别记录。
- 离线演示、fixture 验证、HTTP 模拟与真实 provider 调用分别报告。没有真实运行证据，不宣称 API 可用、模型质量、实际价格或生产效果。
- live 调用需操作者明确选择、凭据和调用上限；默认命令离线。测试和 CI 不使用真实凭据、不调用模型。
- 许可条款由 owner 选择；第三方材料保留原有条款和归属，不能被项目默认许可覆盖。选定后以 `LICENSING.md` 为准。

## 协作与验证

允许多个责任面并行，但一个文件只有一个 writer。临时 worker 只处理工单指定路径，不读取私人连续性或主会话说明，不调用 Oracle、不再派工，不改全局 routing，不 commit/push/发布/部署或操作账号。

本项目统一验证入口由 `python3 tools/check.py` 提供，完整检查先安装 `requirements-site.txt` 并准备 Node.js 22+；浏览器逻辑测试不需要 npm packages。仅核心 CLI/数据检查使用 `--core-only`。provider CI 只调用此入口，不运行模型或部署。源码支持 Python 3.11+；优先标准库，只有当前功能需要时才添加依赖。静态检查不证明视觉质量；修改站点布局/交互时另做桌面与手机的真实浏览器检查。

修改 CLI、记录格式、失败行为时，更新对应实验说明和 README，并验证真实入口；内容改动检查相对链接、来源映射、日期与事实投影。报告 source、测试、live 推理和公开状态时分开。
