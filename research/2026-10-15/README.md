# 2026-10-15 定向更新：原生契约与托管边界

[变化索引](updates.json) · [10-08 历史调查](../2026-10-08/README.md) · [实验玩法](../../docs/playbook.md) · [next-action 实验](../../experiments/next-action/README.md)

本轮在 **2026-10-15** 核对 OpenAI Decisions、TypeSafe Jev 的官方文档与 Python SDK，并对 Fastino、Cloudflare Clef 和 Upstage Solar Decide 做相关契约核对。这是对 10-08 调查的有界增量，**没有重新审查全部 23 个实体、21 个仓库或 171 条来源**。旧快照保留当时的事实；本页和 [updates.json](updates.json) 记录本轮观察到的变化及来源差异。

所有价格都是访问当日的公开标价，所有能力都是明确来源范围内的声明。本轮未使用凭据、未调用模型、未测账单、延迟、中文质量或校准，也未证明任何账号的实际可用性。文档更新、SDK 类型和服务端行为是不同证据。

## 重点变化

| 对象 | 10-08 记录 | 10-15 核对结果 | 对使用者的影响 |
| --- | --- | --- | --- |
| TypeSafe Jev | 1.13；latest 与 preview 均指向 1.13 | 1.14 于 10-14 发布；preview 指向 1.14，latest 仍指向 1.13 | 固定版本仍有意义，不能把 preview 升级当成无行为变化 |
| TypeSafe 扩展 | 文本／JSON、三原语、默认 64k／32k | 文档新增 opt-in 262k 长上下文，以及 Images／Box 实验功能 | 默认文本契约与 danger-zone 扩展分开判断 |
| OpenAI Decisions | 未建立最大问题数；图片仅 inline data URL | reference 与 SDK 都写明 1–200 问题，并接受公开 HTTP(S) 图片 URL | 旧输入限制不能继续当作当前限制 |
| OpenAI reference／SDK | 以当时源代码形状记录 | reference 已列多角色、tool history 与 cache controls；Python main 尚未同步这些类型 | 分别记录文档和 SDK 支持，不能合并成已验证能力 |
| Cloudflare Clef | Flash hosted 64K、$0.090/M 输入 | 10-09 发布 Omni；Flash hosted 变为 24K，当前模型页精确值 24,576；$0.038/M 输入 | hosted 限制变化不代表 Flash 权重的自托管 256K 限制变化 |
| Upstage | 原厂 solar-decide；Flash 直连待核 | 当前 API 仍只列 solar-decide；Choice 2–26，文档给出 27 项返回 422 的示例 | OpenRouter Flash 路线仍不能等同于原厂直连契约 |
| Fastino | GLiDE 与 GLiNER 的两条不同路径 | GLiDE 关键契约与价格相符；catalog 明确 GLiNER-2.5-Decide hosted ID、340M 与 8,192 context | 同为 System One 外形也不能互换 Score 或 confidence 语义 |

表中变化对应下文的原始来源。除 Jev 1.14、Clef Omni 的明确发布日期及 SDK commit 日期外，“10-15 核到”表示观察日期，不推断功能具体上线时间。

## OpenAI Decisions：共同支持部分与来源差异

当前 [guide](https://developers.openai.com/api/docs/guides/decisions) 仍称 Decisions 为 public beta，唯一模型为 `gpt-6-luna`。原生请求是 `POST https://api.openai.com/v1/decisions`，使用 `Authorization: Bearer …`；基本 body 为 `{model,input,questions:[…]}`。支持 `predicate`、`choice`、`score`；答案按问题顺序返回。Choice 有 2–255 个唯一的 string／boolean 值，二者类型不同；Score 是有序 level 下标的概率加权期望。[官方 reference](https://developers.openai.com/api/reference/resources/decisions/methods/create)

当前 reference 和 [Python request types](https://github.com/openai/openai-python/blob/main/src/openai/types/decision_create_params.py) 一致写明每请求 **1–200 questions**。图片可用 base64 data URL 或公开 HTTP(S) URL，每请求最多 128 图，`file_id` 不支持；不是“只能 inline”。SDK 的 [image type](https://github.com/openai/openai-python/blob/main/src/openai/types/decision_input_image_param.py) 同样列出这些 URL 形状。

来源之间仍有差异：

| 能力 | 当前 reference | 本轮读取的 Python main |
| --- | --- | --- |
| 输入角色和历史 | user／developer／system／assistant；function 与 custom-tool calls／outputs | `DecisionInputMessageParam.role` 仍仅 `user`；request docstring 写 tools 不支持 |
| 缓存控制 | `prompt_cache_key`、`prompt_cache_options`、content `prompt_cache_breakpoint` | `create()` 和 request types 未列这些参数 |
| 安全标识 | `safety_identifier` | 已列 `safety_identifier` |

对照源码：[resource](https://github.com/openai/openai-python/blob/main/src/openai/resources/decisions.py)、[message type](https://github.com/openai/openai-python/blob/main/src/openai/types/decision_input_message_param.py)、[request types](https://github.com/openai/openai-python/blob/main/src/openai/types/decision_create_params.py)。main 的 [_version.py](https://github.com/openai/openai-python/blob/main/src/openai/_version.py) 当时为 **3.31.0**；最近涉及所读 request types 的 [d42accb1a2d1b75b79edf694b8bfee78c4e90e6a](https://github.com/openai/openai-python/commit/d42accb1a2d1b75b79edf694b8bfee78c4e90e6a) 日期为 **2026-10-14T17:30:55Z**。这是该文件的修改定位，不是全部 main 文件固定在该 commit 的声明。上述扩展应保留为 reference／SDK drift，本轮没有证明服务端实际接受它们。

Choice 返回 `choice`、`probabilities:[{value,probability}]`、独立 `confidence`。每个问题都可能返回 `type:"refusal"` 和 `name`，同请求其他问题仍可有正常答案；[response types](https://github.com/openai/openai-python/blob/main/src/openai/types/decision.py) 没有 refusal reason 文本字段。不能把拒答、普通 `unknown` 选项和 HTTP／解析失败合并。confidence 的具体计算公式仍未从本轮来源中建立。

当前 [Batch SDK enum](https://github.com/openai/openai-python/blob/main/src/openai/types/batch_create_params.py) 未列 `/v1/decisions`。SDK 的 lazy HTTP response wrapper 也不能证明 Decisions 有事件流契约。本轮不继承模型级 Batch／Flex 折扣，不把模型 context 直接当成 endpoint 已验证上限。

## TypeSafe Jev：稳定文本路径和实验扩展

[Models](https://docs.typesafe.ai/models) 列出 `jev-1.13.0` 与 `jev-1.14.0`，后者明确从 **2026-10-14** 可用；`jev-latest` 仍指向 1.13，`jev-preview` 指向 1.14。默认限制仍为 64k per-request、32k per-question；问题数没有独立上限，只受这两个 token budget 限制。速率限制现按 organization 设置并要求查看 console，旧记录的 100K tokens/s 和 80 requests/s 不能继续当作当前统一承诺。

原生路径仍为 `POST https://api.typesafe.ai/v1/systemone`，Bearer auth；body 的核心为 `{model,state,questions:{…}}`。`state` 可为文本、object 或 array；question ID 只用于关联，官方说明其不进入模型。Choice 使用 `criteria` map，答案以同名 key 返回 `choice`、完整 `probabilities` map 和 `confidence`；Score 返回概率加权下标。当前 [API 总览](https://docs.typesafe.ai/api) 列出 32 MiB body、64 层嵌套、有限数值与压缩限制，以及 400／401／413／415／422／429／529 等错误。`400 max_tokens_exceeded` 已明确表示超过 context，补足旧快照的 oversize unknown。

当前实验扩展必须显式开启：

- **长上下文**：`TypeSafe-Danger-Zone-Long-Context: true` 将 1.13／1.14 的 request 和 question budget 都提高到 262k；官方说明单 token 价格相同，但更慢、准确率较低。[Models](https://docs.typesafe.ai/models)
- **Images**：`TypeSafe-Danger-Zone-Images: true`，通过 top-level `assets` 将图片引用放入 `state`、`instructions` 或 `criteria`。Jev 1.13／1.14 均接受；支持 PNG／JPEG、multipart 或 base64。官方标为 dreamer-ready，尚未达到生产就绪标准，格式和限制仍可变化。[Images](https://docs.typesafe.ai/images)
- **Box**：需要 1.14，返回归一化的 `top/bottom/left/right`。没有 not-found answer；目标不存在也可能返回框，需独立存在性判断。Box 页面把 confidence 写成数值，但 OpenAPI 允许 `number|null`。[Box](https://docs.typesafe.ai/primitives/box)

默认 Models 简表仍写 Text，API 总览仍只展开 Noul／Choice／Score；它们没有完整呈现实验分支。另一个差异是 API 总览称 `instructions` required、Score 2–10 levels，而 [公开 OpenAPI](https://api.typesafe.ai/openapi.json) 与 [Python SDK schema](https://github.com/typesafe-ai/typesafe-sdk-python/blob/main/src/typesafe_sdk/_schemas/models.py) 允许省略／null instructions，Score schema 为 `minItems:1` 且未列最大值。不能由较宽的 schema 推断所有边界都被服务端接受。

本轮公开 OpenAPI 无凭据 GET 为 HTTP 200，`info.version` 为 `0.2.0`，包含 Images／Long-Context headers、assets 和 Box。Python main 的 [pyproject.toml](https://github.com/typesafe-ai/typesafe-sdk-python/blob/main/pyproject.toml) 为 **0.7.5**；本轮未固定其 commit，也未安装或执行 SDK。当前 answer union 没有 refusal；不要从“无所选选项”自行推断拒答。

[Confidence 文档](https://docs.typesafe.ai/confidence) 仍将 Choice confidence 定义为 `(pmax - 1/n) / (1 - 1/n)`；Score 使用相对于最可能 level 的平均绝对距离并以均匀分布归一化；Noul 不带独立 confidence。这些是返回概率的派生统计量，不是另一份正确率估计。

## Fastino、Cloudflare 与 Upstage 的相关边界

**Fastino。** [GLiDE](https://docs.fastino.ai/inference/systemone) 仍使用 `POST https://api.fastino.ai/v1/systemone`，请求模型 `fastino/GLiDE`，响应模型 `glide`；首选 `X-API-Key`，迁移说明也接受 Bearer。每个渲染后的问题限制 40,000 tokens，Choice 2–255，Score 最多 255 levels；不支持 streaming、独立 state batch 或 fine-tuned deployment IDs。`usage.input_tokens` 累计各问题的内部 passes，不能把一个 40K prompt 当作整请求最多只计费 40K。[Choice confidence](https://docs.fastino.ai/concepts/glide-choice) 为 top1−top2；[Score](https://docs.fastino.ai/concepts/glide-score) 的 `score` 是众数下标，`expected_level` 才是期望。它们不能直接替换 Jev 的字段和阈值。

Fastino [model catalog](https://docs.fastino.ai/concepts/models) 现明确 hosted `fastino/GLiNER-2.5-Decide` 为 340M、8,192 context，补足旧记录的 ID／context 未知。该模型的完整 GLiNER 请求契约没有在本轮重审；不能因为同属 Fastino 就继承 GLiDE 的 System One 形状。

**Cloudflare。** [2026-10-09 公告](https://developers.cloudflare.com/changelog/post/2026-10-09-clef-omni-workers-ai/) 发布 Clef Omni，描述为 30B MoE／3B active，支持 WAV／MP3 audio 和 MP4／WebM video 的 data URL。发布与媒体能力是原厂声明，本项目未运行。Flash hosted context 从旧记录的 64K 调为 24K；[当前 Flash 模型页](https://developers.cloudflare.com/ai/models/%40cf/cloudflare/clef-flash/) 精确列为 **24,576**。Flash weights 未变，其自托管 256K 与 hosted 限制是不同事实。Omni 模型页在本轮 Web 访问遇到 redirect loop，没有读到该页的完整 schema，不据公告补写请求字段。

**Upstage。** [System One API](https://console.upstage.ai/api/systemone) 当前唯一列出的 model 为 `solar-decide`，Choice 允许 **2–26** 选项，文档给出 27 项返回 422 的示例；这不是本项目发送的探针。[模型页](https://console.upstage.ai/docs/models/solar-decide) 列出 512K context。OpenRouter 的 Solar Decide Flash 路线不证明原厂已提供同名直连。

## 公开标价短表

以下均为 **2026-10-15 访问时、美元／百万输入 tokens** 的文档标价，不是本项目实际费用。不同供应商的 token 计量、内部 passes、区域与上下文附加条件不能省略。

| 路线 | 输入标价 | 条件与来源 |
| --- | --- | --- |
| OpenAI Decisions／gpt-6-luna | $0.100 | 输出、cache read/write 免费；区域与长上下文乘数适用；仅此 endpoint，[guide](https://developers.openai.com/api/docs/guides/decisions) |
| TypeSafe Jev 1.13／1.14 | $0.042 | 输出免费；long context 单 token 价格相同，[models](https://docs.typesafe.ai/models) |
| Fastino GLiDE | $0.150 | 输出免费；输入累计内部 passes，[pricing](https://docs.fastino.ai/pricing) |
| Fastino GLiNER-2.5-Decide | $0.030 | hosted 标价，不能当作自托管成本，[pricing](https://docs.fastino.ai/pricing) |
| Cloudflare Clef Flash | $0.038 | 原快照 $0.090；hosted context 24,576，[模型页](https://developers.cloudflare.com/ai/models/%40cf/cloudflare/clef-flash/) |
| Cloudflare Clef | $0.240 | hosted 64K，[10-09 公告](https://developers.cloudflare.com/changelog/post/2026-10-09-clef-omni-workers-ai/) |
| Cloudflare Clef Omni | $0.150 | hosted 64K；完整模型页 schema 本轮未读到，[10-09 公告](https://developers.cloudflare.com/changelog/post/2026-10-09-clef-omni-workers-ai/) |
| Upstage solar-decide | $0.100 | 原厂 512K；不外推到 Flash，[模型页](https://console.upstage.ai/docs/models/solar-decide) |

## 为什么本项目继续固定两条文本路线

[next-action 实验](../../experiments/next-action/README.md) 继续使用 `jev-1.13.0` 与 `gpt-6-luna`。固定 1.13 保留既有文本契约和将来版本对照的条件；它仍是官方 latest 的目标。OpenAI 仍只列 gpt-6-luna。两条 collector 请求都是单个文本 Choice，属于当前文档与 SDK 的共同支持部分；本轮新增的图片、长上下文、Box、tool history 和缓存控制不是当前实验承诺。

本轮不静默换默认、不新增 provider、不修改 normalizer。版本存在不说明更适合当前任务，文档差异也不提供自动升级依据。若要比较版本，先保留同一输入、选项、标签和运行条件，再按[实验玩法](../../docs/playbook.md)另开有上限的实验；真实网络调用仍需操作者明确选择。

## 两个可复制的原创文本 Choice 示例

下面用同一段原创合成输入展示两种 wire shape，不含标准答案或私人数据，也不是 CLI `prepare` 的逐字输出。**本页仅展示命令，没有执行。复制执行会向对应 provider 发送输入并产生 live 调用；请先自行配置环境变量凭据，并确认调用与费用。** 若只想离线查看本仓库请求，使用实验说明中的 `prepare`。

TypeSafe：环境变量 `TYPESAFE_API_KEY`，固定 1.13。

```sh
curl --request POST https://api.typesafe.ai/v1/systemone \
  --header "Authorization: Bearer $TYPESAFE_API_KEY" \
  --header "Content-Type: application/json" \
  --data-binary @- <<'JSON'
{
  "model": "jev-1.13.0",
  "state": "一份升级说明声称新版把配置字段 mode 改名为 policy，但没有附上 commit、diff 或上游链接。读者要判断这是否影响现有调用。",
  "questions": {
    "next_action": {
      "type": "choice",
      "instructions": "仅根据输入，下一步最合适的核对动作是什么？",
      "criteria": {
        "inspect_source": "检查输入明确给出的原始来源。",
        "compare_contract": "对照已经提供的接口与调用契约。",
        "read_in_context": "结合已经提供的调用方或运行上下文阅读。",
        "needs_more_context": "先取得当前缺少的具体材料。",
        "unknown": "现有选项均不适合，不猜测。"
      }
    }
  }
}
JSON
```

OpenAI：环境变量 `OPENAI_API_KEY`，使用相同输入和选项。

```sh
curl --request POST https://api.openai.com/v1/decisions \
  --header "Authorization: Bearer $OPENAI_API_KEY" \
  --header "Content-Type: application/json" \
  --data-binary @- <<'JSON'
{
  "model": "gpt-6-luna",
  "input": "一份升级说明声称新版把配置字段 mode 改名为 policy，但没有附上 commit、diff 或上游链接。读者要判断这是否影响现有调用。",
  "questions": [
    {
      "type": "choice",
      "name": "next_action",
      "instructions": "仅根据输入，下一步最合适的核对动作是什么？",
      "choices": [
        {"value": "inspect_source", "description": "检查输入明确给出的原始来源。"},
        {"value": "compare_contract", "description": "对照已经提供的接口与调用契约。"},
        {"value": "read_in_context", "description": "结合已经提供的调用方或运行上下文阅读。"},
        {"value": "needs_more_context", "description": "先取得当前缺少的具体材料。"},
        {"value": "unknown", "description": "现有选项均不适合，不猜测。"}
      ]
    }
  ]
}
JSON
```

`unknown` 是我们提供的普通选项，不是 API refusal。两个返回的 confidence 也不能直接当成同一个指标。返回结果后应保留原始响应、模型版本与调用状态，再决定如何评分；模型的建议不会由本项目自动执行。

## 覆盖、访问结果与未知

本轮直接审读 OpenAI guide／reference 和相关 Python types，TypeSafe models／API／confidence／images／Box／公开 OpenAPI 和 Python SDK；补查 Fastino 的调用、primitive、价格与 model catalog。Cloudflare 与 Upstage 的上述资料由同轮研究交叉纳入。来源 URL、访问日期、证据类型和具体变化见 [updates.json](updates.json)。

公开文档网页成功解析，所列 GitHub Contents API 读取返回 HTTP 200；TypeSafe OpenAPI 也返回 HTTP 200。`raw.githubusercontent.com` 直取出现 SSL unexpected EOF，改由同一原作者仓库的 GitHub Contents API 读取成功。Web 工具不能解析 OpenAI `.md` 的 `text/markdown`，HTML 可读。工具访问障碍不证明产品不可用。

本轮没有重查全部 OpenRouter 目录、全部模型权重、21 个相关仓库或六组研究，没有重跑历史模型与 benchmark。[Cloudflare Omni 模型页](https://developers.cloudflare.com/ai/models/@cf/cloudflare/clef-omni/)遇 redirect loop，[Perplexity 的新请求 guide](https://docs.perplexity.ai/guides/decider) 不可访问，相关完整契约未复核。原始请求形状以外的服务端行为、实际账号权限、地区可用性、SLA、真实速率限制、费用、延迟、中文质量和校准均未验证。

后续最有价值的动作是先选择一个实际问题，固定输入与判定标准，再区分版本比较、协议探针和任务质量实验。可从[实验玩法](../../docs/playbook.md)、[接入设计](../../docs/integration.md)和[评估方法](../../docs/method.md)进入；公开标价与供应商 benchmark 都不能替代这些实验。
