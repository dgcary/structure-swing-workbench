from datetime import datetime
from zoneinfo import ZoneInfo

from app.market_data.akshare_adapter import AKShareProvider
from app.market_data.contracts import DataQuality


def test_missing_security_detail_key_is_not_silent():
    class Frame:
        def __init__(self, rows):
            self.rows = rows

        def to_dict(self, orient):
            return self.rows

    class Client:
        def stock_zh_a_spot_em(self):
            return Frame([{"代码": "600000", "名称": "浦发银行", "最新价": 10}])

        def stock_individual_info_em(self, **kwargs):
            return Frame([{"item": None, "value": "unknown"}])

    now = datetime(2026, 10, 9, 14, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
    result = AKShareProvider(client=Client(), clock=lambda: now).get_security("600000")
    assert result.quality is DataQuality.UNVERIFIED
    assert "industry" in result.missing_fields
    assert result.error is None
