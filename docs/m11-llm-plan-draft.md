# M11｜ChatGPT 自然语言 → 标准交易计划（AI 草稿）

## 目标与边界

用户用自然语言描述交易想法（例："浦发银行 C 类回踩，10 块到 10 块 5 建仓，跌破 9 块 6 止损，三成仓位"），
LLM 适配器把描述**提取**为结构化的计划草稿字段，填入新建计划表单。**草稿不创建计划、不触发审计**——
创建（POST /plans）、提交审计与决策仍走正常流程，AI 永远不可绕过纪律审计。

## 架构边界（architecture.md §4.4，不可违反）

- LLM 只从用户自述文本**提取**字段，不推断、不编造；
- 主观确认字段（`reversal_confirmed`、`structure_invalidated`、
  `remaining_exit_condition_triggered`）**恒为 None**——即使文本声称"已确认反转"，
  也必须由用户在工作台显式设置；
- 枚举取值不合法、数字非法、上沿不高于下沿等一律**丢弃字段并给出中文警告**，不静默纠正。

## 配置

`.env`（OpenAI 兼容 chat completions）：

```dotenv
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=sk-...
```

未配置（`LLM_BASE_URL` 或 `LLM_MODEL` 留空）时 `POST /plans/parse` 返回 503 与中文原因，属预期行为。

## API

`POST /plans/parse`：body `{ "text": "..." }` → `{ "draft": { instrument_code, instrument_name, version_data }, "warnings": [...] }`

- 草稿字段与 `POST /plans` 的 `version` 兼容，前端直接填入新建表单；
- `version_data` 只包含安全字段：价格/百分比（Decimal→字符串）、枚举值、文字说明；
- `warnings` 列出被丢弃或无法解析的内容。

## 前端

「交易计划」页新建表单上方有「AI 草稿」面板：输入自然语言 → 生成草稿 → 自动填入表单并显示警告；
用户核对、补全主观字段（反转确认、结构失效状态）后正常创建计划。

## 验证

`backend/tests/test_api_llm_plan.py`：注入假 LLM completer，覆盖合法 JSON、markdown 围栏、
非法枚举/数字丢弃与警告、上沿不高于下沿、非法 JSON 502、未配置 503，以及
**主观确认字段即使 LLM 返回也被丢弃**的边界。后端 415 个测试全部通过。
