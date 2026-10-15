# 快速变化的信息，怎样持续维护

让变化发生在它所属的表面。可复现性依赖当时的事实留得住；实用性依赖新的事实找得到。

## 三层时间

| 层 | 内容 | 更新方式 |
| --- | --- | --- |
| 方法 | 任务设计、证据分级、校准、接入边界 | 出现改变判断的新证据时修订 |
| 日期快照 | 来源、模型/路线、版本、价格、作者报告 | 新调查放入新的日期目录；历史勘误明确标注 |
| 实验记录 | 输入、profile、模型、输出、用量、错误 | 每次写新目录；原始结果不覆写为新结果 |

`research/2026-10-08/` 是首期快照，`catalog/index.json` 分别声明 `source_root` 和 `latest_update`。后者目前指向 `research/2026-10-15/updates.json`：用变化记录关联来源 ID，保留核查日期、访问结果、未覆盖范围和 live 状态。新增定向增量不重写首期 census，也不代表所有链接已重新检查。`docs/current-state.md` 只描述本项目目前做到了哪里，不承担整份领域百科。

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

更换站点资产后，旧 `_site/` 可能留下已退役的文件；builder 会报 `Unexpected existing output`，不会擅自清空目录。先检查报错路径，确认它仅是旧的生成文件，再移除该文件并重新构建。当前源码不再生成旧版的 `site/orbit.js`。

历史矩阵的三组数字来自 `research/2026-10-08/reanalysis/sys1_reanalysis.json`；交互练习选取 `experiments/next-action/cases.json` 中的三个 dev cases，标签与理由随构建投影。矩阵每格代表一条记录的计数，按汇总结果分组，不声称恢复原始样本身份或顺序。修改这些源时同时检查首页显示；不要在 HTML 或浏览器脚本里另写答案副本。站点脚本变更会生成新的资源版本 URL，供浏览器区分构建后的缓存。完整验证包含无网络 JavaScript 行为检查；排版、手机断行和实际点击仍需浏览器检视。

## 图形与外观的维护边界

`site/sculpture.js` 的 WebGL 粒子作品在编织、分岔、环流间变形，支持指针扰动与冲散；几何和颜色不代表模型关系或性能。无 WebGL 或 context 丢失时保留 SVG，恢复 context 后重新初始化并保留暂停状态。`site/atlas.js` 渐进增强独立的项目分类切换，项目名称、分组和链接由构建器读取 catalog 与带日期的 repositories 快照生成；不另存事实副本。无 JavaScript 时保留首组入口和完整项目目录链接。`site/recipes.js` 增强玩法分类、关键词搜索和复制；无 JavaScript 时全部配方仍可展开阅读。`site/field.js` 的三个高斯山峰由示意候选概率加权，maxP 和 Shannon entropy 使用同一分布计算；几何投影不等于概率校准。`site/evidence.js` 只投影构建时传入的历史汇总，切换高 maxP 时保留完整格子位置并淡化筛选外记录。作品／示意／历史标签需要一起保留。

`site/theme.js` 在样式加载前读取本地外观选择，未选择时跟随系统；只写入 `decisions-theme`，不储存输入或练习答案。接入说明的原创 `site/flow.svg` 在构建时内联，随同一主题变色；原 SVG 仍是唯一编辑源。两幅 Canvas 都提供暂停，遵循减少动态效果偏好，并在后台／视野外停止。无 JavaScript 时保留内嵌 SVG 和静态汇总。

视觉研究参考了 [TypeSafe Jev](https://typesafe.ai/) 的点阵语汇、[tixy](https://tixy.land/) 的参数驱动画面，以及 [Seeing Theory](https://seeing-theory.brown.edu/) 把概率概念做成可操作对象的方式。本项目图形与交互独立实现，未复制上述项目的代码或素材；参考不构成对模型效果的背书。

改动图形时同时看日间、夜间、桌面、手机、静止和运动状态；自动化行为检查不能替代视觉检查。首屏高度、下滑入口、长文阅读和控件反馈应在同一次浏览器检查中连起来使用。

## 新结果要回答什么

记录本次要改变的决策、输入如何选择、分组/切分、baseline、具体路线和模型、未通过案例、原始概率、计时/费用的来源，以及结果不能说明什么。没有 live 运行就写未运行；局部失败也保留。研究贡献可以是复算、反例或修正一个错误解释，不必每次都是排行榜。

维护代码与内容时运行统一入口。GitHub Actions 只负责同一入口的无凭据验证，不运行模型、不发布站点。公开前检查原始导出、私人记录、路径、凭据和第三方许可范围。
