# M6｜StockResearchPack 研究结果只读适配

## 目标与当前范围

本模块仅从 ZIP 研究包读取客观资料和已存在的研究文本，投影为与 TradingAgents 内部实现无关的 `ResearchReport`，并在 Web 工作台展示来源、时间、版本、内容及缺失/错误状态。**研究结果不是交易事实，不产生交易指令，也不进入 M2 纪律审计。**

当前 `/research/sample` 仅提供本仓库内的**固定合成样例**，用于演示“样例 ZIP → 只读适配器 → JSON 投影 → Web 展示”的端到端路径。没有远程 TradingAgents HTTP 客户端、上传服务、持久化、后台调度或真实券商交易。未来真实包接入时先核对 exporter 的实际 schema，再扩展映射；不能将合成样例宣称为真实数据兼容性验证。

## 第一版 ZIP 输入约定（固定合成样例）

ZIP 根目录包含 `manifest.json`，其字段包括：

- `schema_version`：非空版本标识；
- `source`：非空数据来源；
- `generated_at`：带时区的 ISO-8601 时间；
- `files`：可选的 section 名称到 ZIP 内 JSON 文件相对路径映射。

`identity.json` 记录 `symbol`、`name`。各分区可选：`market.json`、`technical.json`、`financial_snapshot.json`（映射为 `fundamental`）、`news.json`、`sentiment.json`、`macro.json`、`bull_research.json`、`bear_research.json`、`evidence.json`、`data_quality.json`。

每个 section 可声明 `status`，取 `OK`、`NO_DATA`、`SOURCE_ERROR`、`MISSING` 或 `INVALID`。没有该字段且 JSON 有效时记为 `OK`，文件缺失记为 `MISSING`，无效 JSON 或未知状态记为 `INVALID`。`NO_DATA` 与 `SOURCE_ERROR` 保持原样，不用空字符串或假数据冒充成功。整体质量只做 `OK` / `PARTIAL` 完整性汇总，不推断股票质量或交易机会。

## 安全与边界

- ZIP 限制压缩体积、文件数、总解压体积和单文件体积；拒绝路径穿越、重复路径和符号链接。
- 不提取文件到磁盘，不请求包内 URL，不执行包内代码，不加载 TradingAgents 内部对象。
- 显示内容不自动转换为 Setup、支撑压力、买卖意见或下单指令。
- 后续远程 HTTP 仅在新任务授权后通过独立输入层实现；`parse_research_pack(bytes)` 是当前可复用的纯解析边界。

## 验证

`backend/tests/test_research_adapter.py` 覆盖固定 ZIP 样例、新闻无数据、情绪来源错误、缺失/损坏分区、路径穿越、重复文件、非法 manifest、时间戳时区及体积限制。`backend/tests/test_research_api.py` 验证固定样例的只读 Web JSON 输出。

演示：启动 `docker compose up --build`，访问 Web 首页的“研究资料（只读演示）”。样例证券名称、价格和财务数据均为合成测试值，不可用于投资判断。
