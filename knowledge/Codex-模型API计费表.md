# Codex 模型 API 计费表

本文是 AGENTS 看板使用的模型标识映射、标准 API Token 单价、长上下文附加规则和费用计算公式的唯一依据。[`SPEC-UI-009`](../reference/SPEC/ap01-1.0.2_0031-opt.bin.md#spec-ui-009-今日消耗) 与 [`技术实现`](../reference/DESIGN/ap01-1.0.2_0031-opt.bin技术实现/ap01-1.0.2_0031-opt.bin技术实现.md#72-采集链路) 只引用本文，不复制或改写表内单价和公式。

API 等价成本表示：如果相同的模型 Token 明细按照官方标准 API 单价计费，需要支付多少美元。它用于统一衡量用量，不代表 Codex 订阅账户当天实际扣款。GPT（Codex 使用的一组模型名称）的单价均为每 100 万 Token 的美元价格。

| 本地模型标识 | 官方计费名称 | 普通输入 | 缓存输入 | 缓存写入 | 输出 | 长上下文规则 | 计费状态 |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| `gpt-5.6` | GPT-5.6 Sol | $5.00 | $0.50 | $6.25 | $30.00 | 输入超过 272,000 时，全部输入 2 倍、输出 1.5 倍 | 可计算 |
| `gpt-5.6-sol` | GPT-5.6 Sol | $5.00 | $0.50 | $6.25 | $30.00 | 输入超过 272,000 时，全部输入 2 倍、输出 1.5 倍 | 可计算 |
| `gpt-5.6-terra` | GPT-5.6 Terra | $2.50 | $0.25 | $3.125 | $15.00 | 输入超过 272,000 时，全部输入 2 倍、输出 1.5 倍 | 可计算 |
| `gpt-5.6-luna` | GPT-5.6 Luna | $1.00 | $0.10 | $1.25 | $6.00 | 输入超过 272,000 时，全部输入 2 倍、输出 1.5 倍 | 可计算 |
| `gpt-5.5` | GPT-5.5 | $5.00 | $0.50 | 按普通输入 | $30.00 | 输入超过 272,000 时，全部输入 2 倍、输出 1.5 倍 | 可计算 |
| `gpt-5.4` | GPT-5.4 | $2.50 | $0.25 | 按普通输入 | $15.00 | 输入超过 272,000 时，全部输入 2 倍、输出 1.5 倍 | 可计算 |
| `gpt-5.4-mini` | GPT-5.4 mini | $0.75 | $0.075 | 按普通输入 | $4.50 | 无附加规则 | 可计算 |
| `gpt-5.3-codex` | GPT-5.3-Codex | $1.75 | $0.175 | 按普通输入 | $14.00 | 无附加规则 | 可计算 |
| `codex-auto-review` | GPT-5.3-Codex | $1.75 | $0.175 | 按普通输入 | $14.00 | 无附加规则 | 可计算 |
| `gpt-5.2` | GPT-5.2 | $1.75 | $0.175 | 按普通输入 | $14.00 | 无附加规则 | 可计算 |
| `gpt-5.2-codex` | GPT-5.2-Codex | $1.75 | $0.175 | 按普通输入 | $14.00 | 无附加规则 | 可计算 |
| `gpt-5.5-cyber` | GPT-5.5 Cyber | 未公布 | 未公布 | 未公布 | 未公布 | 未公布 | 无法计算 |
| `gpt-5.3-codex-spark` | GPT-5.3-Codex-Spark | 未公布 | 未公布 | 未公布 | 未公布 | 未公布 | 无法计算 |

`gpt-5.6` 是官方明确指向 GPT-5.6 Sol 的别名。`codex-auto-review` 使用 GPT-5.3-Codex 单价，因为官方说明代码审查使用 GPT-5.3-Codex。GPT-5.6 系列的缓存写入按普通输入单价的 1.25 倍计算；其他表内模型没有公布独立缓存写入价时，缓存写入按普通输入价计算。

每次模型请求先按原始字段拆分：

```text
普通输入 Token =
原始输入 Token - 缓存命中 Token - 缓存写入 Token
```

普通输入不得小于零。每次请求的标准 API 等价成本按下式计算：

```text
本次精确费用 =
(
  普通输入 Token × 普通输入单价
  + 缓存命中 Token × 缓存输入单价
  + 缓存写入 Token × 缓存写入单价
  + 输出 Token × 输出单价
) ÷ 1,000,000
```

表内声明长上下文规则的模型，如果该次请求的原始输入超过 272,000 Token，则该次请求的普通输入、缓存输入和缓存写入费用均乘 2，输出费用乘 1.5。必须逐次请求判断，不能先按天汇总 Token 后再判断。

推理输出 Token 已包含在输出 Token 中，不重复计费。同一天使用多个模型时，先逐次计算未取整费用，再按模型汇总并求出当天总和；图片最后只把当天总和四舍五入为整数美元。只要当天存在一次无法确定模型、单价或必要 Token 字段的正用量，当天费用就显示“无法获取”，不能显示已知部分的小计冒充总计。

本表只计算标准 API 的文本 Token 费用，不套用批量、弹性、优先处理、地区处理或 Codex 积分规则。网页搜索、电脑操作、图片生成等按调用次数或其他单位单独计费的工具，如果本地原始记录没有返回完整计费单位，不计入本表结果，界面字段必须称为“API 成本”，不能称为账户实际扣款。

## 官方来源与维护

| 模型或规则 | 官方来源 |
| --- | --- |
| GPT-5.6 Sol | [模型与价格](https://developers.openai.com/api/docs/models/gpt-5.6-sol) |
| GPT-5.6 Terra | [模型与价格](https://developers.openai.com/api/docs/models/gpt-5.6-terra) |
| GPT-5.6 Luna | [模型与价格](https://developers.openai.com/api/docs/models/gpt-5.6-luna) |
| GPT-5.5 | [模型与价格](https://developers.openai.com/api/docs/models/gpt-5.5) |
| GPT-5.4 | [模型与价格](https://developers.openai.com/api/docs/models/gpt-5.4) |
| GPT-5.4 mini | [模型与价格](https://developers.openai.com/api/docs/models/gpt-5.4-mini) |
| GPT-5.3-Codex | [模型与价格](https://developers.openai.com/api/docs/models/gpt-5.3-codex) |
| GPT-5.2 | [模型与价格](https://developers.openai.com/api/docs/models/gpt-5.2) |
| GPT-5.2-Codex | [模型与价格](https://developers.openai.com/api/docs/models/gpt-5.2-codex) |
| `codex-auto-review` 模型映射 | [Codex 计费说明](https://help.openai.com/en/articles/20001106-codex-rate-card) |
| 本次核验日期 | 2026-07-28 |
| 运行方式 | 运行时使用仓库内已经核验的固定表，不联网抓取价格 |

官方价格、模型名称或附加计费规则发生变化时，必须在同一次变更中更新本文、计费实现和自动测试；其他文档继续只引用本文。
