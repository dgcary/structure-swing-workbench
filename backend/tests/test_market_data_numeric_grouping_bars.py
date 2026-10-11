"""M4 regression: numeric grouping is validated in historical OHLCV too."""

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.market_data.akshare_adapter import AKShareProvider
from app.market_data.contracts import DataQuality, Timeframe


NOW = datetime(2026, 10, 9, 14, 30, tzinfo=ZoneInfo("Asia/Shanghai"))


class Frame:
    def __init__(self, row):
        self.row = row

    def to_dict(self, orient):
        assert orient == "records"
        return [self.row]


class Client:
    def __init__(self, field, value):
        self.row = {
            "时间": "2026-10-09 14:25:00",
            "开盘": 10,
            "最高": 11,
            "最低": 9,
            "收盘": 10,
            "成交量": 1000,
            "成交额": 10000,
        }
        self.row[field] = value

    def stock_zh_a_hist_min_em(self, **kwargs):
        assert kwargs["period"] in ("5", "15")
        return Frame(self.row)


@pytest.mark.parametrize("field,raw", [
    ("成交量", "1,2"),
    ("成交量", "12,34"),
    ("成交额", "1,234,56"),
    ("成交额", "1234,567"),
    ("成交额", "1,23e2"),
])
def test_bad_grouping_in_minute_bars_is_error(field, raw):
    provider = AKShareProvider(client=Client(field, raw), clock=lambda: NOW)
    result = provider.get_bars("600000", Timeframe.MIN5)
    assert result.quality is DataQuality.ERROR
    assert result.value is None
    assert "invalid numeric grouping" in result.error


@pytest.mark.parametrize("field,raw,expected", [
    ("成交量", "1,234", Decimal("1234")),
    ("成交额", "12,345.67", Decimal("12345.67")),
])
def test_valid_grouping_in_minute_bars_preserves_values(field, raw, expected):
    provider = AKShareProvider(client=Client(field, raw), clock=lambda: NOW)
    result = provider.get_bars("600000", Timeframe.MIN15)
    assert result.quality is DataQuality.FRESH
    assert getattr(result.value[0], "volume" if field == "成交量" else "amount") == expected
