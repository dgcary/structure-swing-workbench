"""Regression tests: malformed numeric separators must never become prices."""
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.market_data.akshare_adapter import AKShareProvider
from app.market_data.contracts import DataQuality


class Frame:
    def __init__(self, rows):
        self.rows = rows

    def to_dict(self, orient):
        assert orient == "records"
        return self.rows


class Client:
    def __init__(self, amount):
        self.amount = amount

    def stock_zh_a_spot_em(self):
        return Frame([{
            "代码": "600000", "名称": "浦发银行",
            "最新价": 10, "今开": 10, "最高": 10, "最低": 10,
            "成交额": self.amount,
            "更新时间": "2026-10-09 14:29:00",
        }])


NOW = datetime(2026, 10, 9, 14, 30, tzinfo=ZoneInfo("Asia/Shanghai"))


@pytest.mark.parametrize("raw", ["1,2", "12,34", "1,234,56", "1234,567", "1,23e2"])
def test_malformed_grouped_amount_is_error(raw):
    result = AKShareProvider(client=Client(raw), clock=lambda: NOW).get_quote("600000")
    assert result.quality is DataQuality.ERROR
    assert result.value is None
    assert "numeric grouping" in result.error


@pytest.mark.parametrize("raw,expected", [
    ("1,234", Decimal("1234")),
    ("1,234.56", Decimal("1234.56")),
    ("1,234,567.89", Decimal("1234567.89")),
])
def test_valid_grouped_amount_is_preserved(raw, expected):
    result = AKShareProvider(client=Client(raw), clock=lambda: NOW).get_quote("600000")
    assert result.quality is DataQuality.FRESH
    assert result.value.amount == expected
