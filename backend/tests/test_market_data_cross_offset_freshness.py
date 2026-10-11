"""M4 regression: source-time freshness is based on instants, not wall clocks."""
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
    def __init__(self, stamp):
        self.stamp = stamp

    def stock_zh_a_spot_em(self):
        return Rows([{
            "代码": "600000", "名称": "浦发银行",
            "最新价": 10, "今开": 10, "最高": 10, "最低": 10,
            "更新时间": self.stamp,
        }])

    def stock_zh_a_hist_min_em(self, **kwargs):
        return Rows([{
            "时间": self.stamp, "开盘": 10,
            "最高": 10, "最低": 10, "收盘": 10,
        }])


def test_quote_and_minute_bar_stale_across_timezone_offsets():
    # 06:00 UTC is 14:00 China time: stale for both 15m quote and 45m bars?
    # Use 05:00 UTC (13:00 China) so both windows are exceeded.
    provider = AKShareProvider(client=Client("2026-10-09T05:00:00+00:00"),
                               clock=lambda: NOW)
    quote = provider.get_quote("600000")
    bars = provider.get_bars("600000", Timeframe.MIN5)
    assert quote.quality is DataQuality.STALE
    assert bars.quality is DataQuality.STALE
    assert quote.value is not None
    assert bars.value is not None


def test_offset_observation_is_preserved_without_rewriting_source_time():
    provider = AKShareProvider(client=Client("2026-10-09T06:29:00+00:00"),
                               clock=lambda: NOW)
    quote = provider.get_quote("600000")
    assert quote.quality is DataQuality.FRESH
    assert quote.observed_at.utcoffset().total_seconds() == 0
    assert quote.fetched_at.utcoffset().total_seconds() == 8 * 3600
