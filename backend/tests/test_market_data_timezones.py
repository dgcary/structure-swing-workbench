"""M4 provider source-time boundary tests."""
from datetime import datetime
from zoneinfo import ZoneInfo

from app.market_data.akshare_adapter import AKShareProvider
from app.market_data.contracts import DataQuality, Timeframe

NOW = datetime(2026, 10, 9, 14, 30, tzinfo=ZoneInfo("Asia/Shanghai"))


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def to_dict(self, orient):
        assert orient == "records"
        return self.rows


class Client:
    def __init__(self, timestamp):
        self.timestamp = timestamp

    def stock_zh_a_spot_em(self):
        return Rows([{
            "代码": "600000", "名称": "浦发银行",
            "最新价": 10, "今开": 10, "最高": 10, "最低": 10,
            "更新时间": self.timestamp,
        }])

    def stock_zh_a_hist_min_em(self, **kwargs):
        return Rows([{
            "时间": self.timestamp, "开盘": 10,
            "最高": 10, "最低": 10, "收盘": 10,
        }])


def test_future_source_time_is_error_with_reason_for_quote_and_bar():
    adapter = AKShareProvider(
        client=Client("2026-10-09T06:36:00+00:00"), clock=lambda: NOW
    )
    for result in (
        adapter.get_quote("600000"),
        adapter.get_bars("600000", Timeframe.MIN5),
    ):
        assert result.quality is DataQuality.ERROR
        assert result.value is None
        assert "ahead of fetch time" in result.error


def test_utc_offset_source_time_maps_to_china_clock():
    adapter = AKShareProvider(
        client=Client("2026-10-09T06:29:00+00:00"), clock=lambda: NOW
    )
    assert adapter.get_quote("600000").quality is DataQuality.FRESH
    assert adapter.get_bars("600000", Timeframe.MIN5).quality is DataQuality.FRESH
