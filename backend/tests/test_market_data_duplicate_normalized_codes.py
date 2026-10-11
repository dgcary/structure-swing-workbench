"""Duplicate upstream identifiers must not produce ambiguous quote/security facts."""
from datetime import datetime
from zoneinfo import ZoneInfo

from app.market_data.akshare_adapter import AKShareProvider
from app.market_data.contracts import DataQuality


class Rows:
    def to_dict(self, orient):
        assert orient == "records"
        return [
            {"代码": 1.0, "名称": "first", "最新价": 10},
            {"代码": "000001", "名称": "second", "最新价": 11},
        ]


class Client:
    def stock_zh_a_spot_em(self):
        return Rows()


def test_normalized_duplicate_codes_are_rejected_for_quote_and_security():
    now = datetime(2026, 10, 9, 14, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
    provider = AKShareProvider(client=Client(), clock=lambda: now)

    for result in (provider.get_quote("000001"), provider.get_security("000001")):
        assert result.value is None
        assert result.quality is DataQuality.ERROR
        assert "duplicate quote rows" in result.error
