# 许可与归属

本项目是 source-available 研究与实践项目。公开可见不表示全部材料具有同一种许可，也不表示 OSI open source。

| 材料 | 范围 | 条款 |
| --- | --- | --- |
| 原创功能代码与配置 | `decision_lab/`、`tools/*.py`、`site/` 中功能代码与样式、`tests/`、CI；研究中的独立复算 Python 脚本 | [SUL-1.0](LICENSE) |
| 原创文字、研究编排和图示 | README、AGENTS、`docs/`、实验说明、研究报告，以及结构化记录中原创的描述和组织 | [CC BY-NC-SA 4.0](LICENSE-DOCUMENTATION.md) |
| 原创合成实验输入与编辑标签 | `experiments/next-action/` 的数据与 task contract | CC BY-NC-SA 4.0；功能实现仍用 SUL-1.0 |
| 第三方事实、引用、模型和资料 | 各记录链接的原厂文档、原作者仓库、模型卡、论文及引用部分 | 保留原作者权利；本项目不为第三方内容另行授权 |
| 历史研究汇总 | `research/2026-10-08/reanalysis/author_numbers.json` 及其所支持的汇总 | Jiawei Li / sys1-eval 的研究成果；见下文；项目许可不重新授权其底层响应或数据 |

SUL-1.0 允许个人、非商业及内部业务使用；向他人分发或提供须免费且非商业。CC BY-NC-SA 4.0 对原创内容的分享与改编设有署名、非商业及相同方式共享条件。以上是导读，完整条款分别以所链接文本为准。

## 历史研究与上游边界

历史预测来源：Jiawei Li (2026), *Fast Models, Slow Evidence*， [David-DL-Space/sys1-eval](https://github.com/David-DL-Space/sys1-eval)。其代码为 MIT；[DATA_LICENSE.md](https://github.com/David-DL-Space/sys1-eval/blob/main/DATA_LICENSE.md) 将模型输出标为 CC BY 4.0，并保留 provider terms 条件；底层 benchmark 仍各有条款。该文件于 2026-10-09 再次查阅。

本仓库保存归属明确的数字汇总、来源定位和独立复算程序，**不分发历史逐条响应投影、benchmark 原文、工具描述或 reasoning**。复算需要操作者自行提供该调查的证据包或相应投影；程序不会下载或执行包内代码。来源 revision 与投影范围见 [provenance](research/2026-10-08/reanalysis/provenance.json)。

网页中的标价、模型名、API 字段等事实不因编排而成为本项目独占材料。上游许可声明是带日期的研究记录，不能代替采用具体版本前的许可核对。引用链接不表示我们与相关厂商有合作或背书。

## 贡献

欢迎在 issue 中给出公开一手来源、可复现的合成失败案例或勘误。不要提交凭据、账号资料、私人输入或无法再分发的模型记录。代码贡献保留作者权利并适用其路径的 SUL-1.0，原创文字与图示适用 CC BY-NC-SA 4.0；新增第三方内容须说明来源和独立条款。不推定著作权转让。
