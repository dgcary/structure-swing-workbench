"""M4: normalized source codes cannot silently double-count one security."""
from datetime import datetime
from zoneinfo import ZoneInfo

from app.market_data.akshare_adapter import AKShareProvider
from app.market_data.contracts import DataQuality

NOW = datetime(2026, 10, 9, 14, 30, tzinfo=ZoneInfo("Asia/Shanghai"))


class Frame:
    def __init__(self, rows):
        self.rows = rows

    def to_dict(self, orient):
        assert orient == "records"
        return self.rows


class Client:
    def __init__(self, codes):
        self.codes = codes

    def stock_zh_a_spot_em(self):
        return Frame([
            {
                "代码": code, "名称": "测试证券", "最新价": 10,
                "昨收": 10, "今开": 10, "最高": 10, "最低": 10,
                "更新时间": "2026-10-09 14:29:00",
            }
            for code in self.codes
        ])


def test_same_security_in_distinct_source_code_formats_is_duplicate():
    result = AKShareProvider(
        client=Client(["000001", 1.0]), clock=lambda: NOW
    ).get_quote("000001")
    assert result.quality is DataQuality.ERROR
    assert result.value is None
    assert "duplicate quote rows" in result.error


def test_unrelated_source_code_does_not_contaminate_selected_security():
    result = AKShareProvider(
        client=Client(["000001", "000002"]), clock=lambda: NOW
    ).get_quote("000001")
    assert result.quality is DataQuality.FRESH
    assert result.value.symbol == "000001"


def test_malformed_source_code_does_not_become_a_valid_quote():
    result = AKShareProvider(
        client=Client(["1.5", "000002"]), clock=lambda: NOW
    ).get_quote("000001")
    assert result.quality is DataQuality.MISSING
    assert result.value is None
