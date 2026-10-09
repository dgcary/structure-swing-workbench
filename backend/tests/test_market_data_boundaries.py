"""M4 deterministic validation of invalid market data and bad timeframes."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.market_data.akshare_adapter import AKShareProvider
from app.market_data.contracts import DataQuality

NOW = datetime(2026, 10, 9, 14, 30, tzinfo=ZoneInfo("Asia/Shanghai"))


class Rows:
    def __init__(self, records):
        self.records = records

    def to_dict(self, orient):
        assert orient == "records"
        return self.records


class QuoteClient:
    def __init__(self, override):
        row = {
            "代码": "600000", "名称": "浦发银行", "最新价": 10.5,
            "昨收": 10, "今开": 10.2, "最高": 10.8, "最低": 10.1,
            "成交量": 100, "换手率": 1.2,
            "更新时间": "2026-10-09 14:29:00",
        }
        row.update(override)
        self.row = row

    def stock_zh_a_spot_em(self):
        return Rows([self.row])


@pytest.mark.parametrize("field,value,expected", [
    ("最新价", -1, "quote last is negative"),
    ("最高", 8, "quote high is below low"),
    ("最新价", 12, "quote last is outside high/low"),
    ("成交量", -1, "quote volume is negative"),
    ("换手率", -0.1, "quote turnover_pct is negative"),
])
def test_invalid_quote_is_explicit_error(field, value, expected):
    adapter = AKShareProvider(client=QuoteClient({field: value}), clock=lambda: NOW)
    result = adapter.get_quote("600000")
    assert result.quality is DataQuality.ERROR
    assert result.value is None
    assert expected in result.error


@pytest.mark.parametrize("timeframe", ["5m", "2m", None, 5])
def test_bad_timeframe_returns_error(timeframe):
    adapter = AKShareProvider(client=QuoteClient({}), clock=lambda: NOW)
    result = adapter.get_bars("600000", timeframe)
    assert result.quality is DataQuality.ERROR
    assert result.value is None
    assert result.error == "unsupported timeframe"
