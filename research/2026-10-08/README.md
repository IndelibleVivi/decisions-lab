# 2026-10-08 研究快照

[阅读正文](report.md) · [全部来源](source_index.json) · [模型与路线](census.json) · [相关仓库](repositories.json) · [六组研究与实践](practice_evidence.json) · [待核线索](watchlist.json)

这是 2026-10-08 UTC 截点的独立公开资料调查，2026-10-09 整理为仓库中的可编辑版本。包括 23 个模型家族／产品／研究实体、21 个相关仓库和六组研究。实体数不是独立训练厂商数；来源审读不等于运行验证。报告的完整九个正文部分保留，原 HTML 附录的详细记录在本目录 JSON 中。

## 实际执行过什么

对调查包内 1,000 个历史案例、4,000 份保存预测执行离线算术；14 项作者汇总对照相符。2026-10-09 在本项目建立时再次运行两个独立复算脚本，输出 JSON 与原包所交付结果整体一致。

这是附件数据上的再计算。未重新采样模型、未重新从上游取回全部原始数据来检验投影、未验证当前 API 的准确率、中文质量、延迟、账单或账户可用性。概率保留原始舍入，不做重新归一化。模型路由的顺序干预同时改变了问题组成，其混杂和历史目标模型条件保留在报告中。

## 离线复算

Python 3.11+，不需要第三方依赖。价格与概率公式可以直接重算：

```sh
python3 research/2026-10-08/calculations.py --out runs/arithmetic.json
```

历史逐条响应不随本仓库分发。若已持有 `decision_api_evidence_2026-10-08.zip`，可显式提供它：

```sh
python3 tools/reproduce.py --bundle /path/to/decision_api_evidence_2026-10-08.zip --out runs/historical-reanalysis
```

该命令只从 ZIP 读取明确指定的数据条目，在临时目录用**仓库内**审读过的脚本复算；不执行 ZIP 中的 Python、不联网、不改变原包。输出目录必须是新目录。结果与已提交汇总比较；差异会以非零退出码报告，不能替换掉参考结果使其通过。公开原始资料、固定 Git blob 和投影方法见 [provenance.json](reanalysis/provenance.json)。

## 各文件的职责

| 文件 | 内容 |
| --- | --- |
| `report.md` | 冻结日期的综合研究正文；不是当前价格保证 |
| `census.json` | 模型、原厂、托管路线、本地路径、限制、unknowns |
| `repositories.json` | 原作者仓库、具体机制、审读深度、版本与限制 |
| `practice_evidence.json` | 六组研究的测量、标签、条件与局限 |
| `source_index.json` | URL、来源别名和核验日期 |
| `openrouter_routes.json` | 当日网关目录，不能当作独立模型数量 |
| `openai_decisions_record.json` / `llamacpp_route.json` | 两条路线的专项契约记录 |
| `public_probe_protocol.json` | 12 项尚未运行的契约探针、六份原创合成文本 |
| `watchlist.json` | 尚未完成原厂追溯的线索及相邻范围 |
| `calculations.py` / `calculations.json` | 带假设的成本、概率公式演算 |
| `reanalysis/` | 独立重算代码、作者汇总、来源定位及离线结果 |
| `metadata.json` / `verification.json` | 原调查数量与计算检查范围 |
| `report_verification.json` | 原 HTML 的静态检查记录；`browser_rendered:false` 是该历史产物的状态 |
| `import-manifest.json` | 从研究包到此快照的明确纳入、排除与编辑转换 |

## 来源、编辑与维护

Faye 发起研究，AI 辅助采集与整理，Faye & Cove 编辑为可分享的研究作品。文章里的原作者数字和实现归属于对应来源；所有本轮复算仅声称其明确执行范围。原始私人对话不作为公开资料，也不随本仓库分发。

导入时将内部工具 reference ID 转为公开来源链接，去除机器路径和内部派工用语；正文来源链接解析为完整 URL。报告的调查日期、数据和判断边界不被导入日期覆盖。新事实进入后续快照；本版错误通过带说明的勘误修订，不能静默把历史模型换成当前模型。

重做格式导入仅需可选的 `tools/requirements-import.txt`，并用 `tools/import_snapshot.py --bundle ... --dest <new-directory>` 写到新目录。正常阅读、实验和 site 构建不需要这个导入依赖。许可边界见 [LICENSING](../../LICENSING.md)。
