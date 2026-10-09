# M4 行情适配层

此模块只提供客观行情、证券元数据、数据质量和确定性数学派生值，不做趋势、支撑、Setup 或买卖判断。审计/持仓引擎不依赖 AKShare。

## 标准接口

`MarketDataProvider` 定义 `get_quote(symbol)`、`get_bars(symbol, timeframe)`、`get_security(symbol)`，每次调用均返回 `DataResult[T]`。

`Quote` 包含代码、名称、最新价、昨收、当日 OHLC、涨跌幅、涨跌停价、量额、换手率、振幅；`Bar` 支持日K、5分钟、15分钟K；`SecurityInfo` 提供行业、交易所、停牌、ST 与退市风险字段。没有可靠来源的字段保持 `None`，并列入 `missing_fields`。

`DataResult` 保留数据源、获取时间 `fetched_at`、**源观测时间** `observed_at`、质量与错误。质量状态：

- `FRESH`：源观测时间明确且未超出允许延迟。
- `STALE`：源观测时间明确，但超过新鲜度阈值。
- `UNVERIFIED`：源未提供可核实的精确观测时间。获取时间不能替代源时间。
- `MISSING`：未找到目标或数据为空。
- `ERROR`：上游调用失败、字段非法或源时间明显超前。

某些字段缺失时可保留其他已取得的客观字段，但必须通过 `missing_fields` 显示；不能自动补成 0 或猜测。所有时间使用带时区的 `datetime`，A 股源中无时区的时间按上海时区解析。

## AKShare 适配

`AKShareProvider` 默认使用 `stock_zh_a_spot_em` 获取沪深京 A 股快照，`stock_zh_a_hist` 获取日线，`stock_zh_a_hist_min_em` 获取 5/15 分钟线，`stock_individual_info_em` 获取证券基础信息。实际源接口可随 AKShare 版本变化，调用失败必须返回明确错误，不得回退为虚构数据。

安装可选依赖：在 `backend` 目录运行 `pip install '.[market]'`。核心测试不安装/访问 AKShare，向构造器注入假客户端与固定时钟。公网 smoke test 应单独运行，不属于普通 CI。

**已知边界**：AKShare 东方财富快照不一定提供涨跌停价或可靠源观测时间，缺失时保留空值/标记 `UNVERIFIED`；日线常只有日期而非精确发布时间，不能据获取时间冒充实时。证券停牌/退市风险没有直接可信字段时保留未知。ST 只依据证券简称公开标记，不等于自动认定退市风险。

数学派生值 `moving_average` 和 `period_extrema` 只计算用户指定窗口的均值、最高价和最低价；数据不足返回 `None`。不在本阶段实现筹码估算、账户 CSV、行情趋势分类或自动交易。
