# Decisions Lab

**把有限选项的判断，变成可以检查的实验。**

[English](README.en.md) · [研究快照](research/2026-10-08/README.md) · [项目地图](docs/projects.md) · [运行实验](experiments/next-action/README.md) · [当前状态](docs/current-state.md)

Decisions Lab 研究 decision models 与 typed decision APIs：它们接受证据和明确的选项，返回结构化判断。我们关心接口承诺了什么、错误发生在哪里，以及怎样把判断接入一个仍由人和代码负责的工作流。

这里有三种不同寿命的内容：可持续使用的方法、带日期的调查、可以重新运行的实验。版本和价格会变；当时的来源、请求和结论不应跟着消失。

## 先做哪件事

| 你想做什么 | 从这里开始 |
| --- | --- |
| 理解这个领域和证据边界 | [2026-10-08 调查及复算](research/2026-10-08/README.md) |
| 找 SDK、开放模型、运行时或评测项目 | [按问题分组的项目地图](docs/projects.md) |
| 真正运行一个判断任务 | [next-action 实验](experiments/next-action/README.md) |
| 决定怎样接入自己的工作流 | [接入设计](docs/integration.md) |
| 更新快速变化的资料 | [维护方法](docs/maintenance.md) |

## 五分钟跑通离线实验

需要 Python 3.11+，核心 CLI 无第三方依赖。在仓库根目录运行：

```bash
python3 -m decision_lab validate experiments/next-action/cases.json
python3 -m decision_lab baseline-run experiments/next-action/cases.json --run-dir runs/baseline-001
python3 -m decision_lab demo experiments/next-action/cases.json --run-dir runs/demo-001
python3 -m decision_lab replay runs/demo-001 experiments/next-action/cases.json
```

任务是：给定文档/变更和一个主张，推荐下一步核对动作。25 个原创合成用例覆盖中文、英文与混写；同一来源的变体保持在同一个 dev/test 分组。baseline 使用确定性规则；demo 有意构造一个错误和一个 unknown。**这些都不是模型实测，也不构成质量排名。** 每次使用新运行目录，以保留旧记录。

```bash
# 检查两条原生 API 的请求，不发送
python3 -m decision_lab prepare experiments/next-action/cases.json --route jev --limit 1
python3 -m decision_lab prepare experiments/next-action/cases.json --route decisions --limit 1

# 离线查询调查记录
python3 tools/catalog.py projects --query calibration
python3 tools/catalog.py models --query clef --json
```

live collector 支持 TypeSafe Jev 与 OpenAI Decisions 的原生 HTTP 形状；需要操作者主动选择网络调用、配置环境变量凭据并给出调用上限。具体命令与限制见[实验说明](experiments/next-action/README.md)。本项目目前没有 live 推理或生产接入证据，不能据此声称某个账号、区域或模型可用。

## 阅读站与验证

阅读站从同一份 Markdown 和 catalog 构建。首页以全屏生成式粒子场开场，下滑进入研究索引与交互实验。概率地形可以切换示意分布、调整候选偏向，并查看 maxP 和熵；历史像素矩阵可切换三组任务及高 maxP 子集，显示对应正确／错误数量。三个原创合成案例允许选择下一步动作、查看编辑标签和理由。首屏作品与概率地形均不是模型输出。长文支持章节目录、阅读进度、代码复制和表格内横向滚动；项目地图可检索并跳到匹配行，原有局限和来源说明始终保留。

浏览器不请求模型，不加载外部字体、分析脚本或 CDN，不保存练习答案；仅在本地保存手动选择的日／夜外观。默认外观跟随系统，所有阅读页共用同一选择。动态作品可暂停，并尊重系统减少动态效果偏好；页面后台或作品滚出视野时停止动画。关闭 JavaScript 后保留静态图、历史汇总、正文与案例材料。构建需要 Python 3.11+ 与 `requirements-site.txt`；完整验证另外需要 Node.js 22+，无需安装 npm packages。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-site.txt
.venv/bin/python tools/check.py
.venv/bin/python tools/build_site.py
python3 -m http.server 8765 --bind 127.0.0.1 --directory _site
```

打开 `http://127.0.0.1:8765`。`_site/` 是派生输出；构建器只发布显式列出的正文、公共研究文件与站点资源。只验证核心 CLI 和数据时，可用标准库执行 `python3 tools/check.py --core-only`。CI 的唯一入口也是 `tools/check.py`。

## 证据与限制

首期调查包含 23 个模型/服务实体、21 个相关仓库、6 项研究、171 条来源索引。我们复算了随包历史输入：1,000 个案例、4,000 条概率记录，14 项作者汇总核对一致。原始预测记录不随仓库分发；有原始 evidence bundle 的读者可以按[复算说明](research/2026-10-08/README.md)检查。

这些是特定任务与历史版本的证据。选项集合、语言、上下文截断、问题依赖和 confidence 定义都会改变解释。高 maxP 不能替代针对实际任务的校准；unknown、API refusal 和错误也不能混记成“否”。[评估方法](docs/method.md)说明如何读结果。

## 数据边界与许可

公共内容使用公开来源或原创合成任务。原始 chat、私人项目上下文、凭据与真实运行记录不进入 Git。collector 会把选择的任务输入发送给对应 provider；运行记录保留任务关联和原始响应，真实输入的记录应按输入的敏感程度保管。模型建议不会自动执行，不写入个人记忆或修改项目。

原创代码：[SUL-1.0](LICENSE)。原创文档、图示与合成案例：[CC BY-NC-SA 4.0](LICENSE-DOCUMENTATION.md)。第三方模型、数据和引用材料保留其自身条款；详细范围与归属见 [LICENSING.md](LICENSING.md)。这不是 OSI open-source 许可声明。
