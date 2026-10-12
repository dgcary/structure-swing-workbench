"""Market data regression: duplicate source instants with different offsets."""
from datetime import datetime
from zoneinfo import ZoneInfo

from app.market_data.akshare_adapter import AKShareProvider
from app.market_data.contracts import DataQuality, Timeframe


class Frame:
    def to_dict(self, orient):
        assert orient == "records"
        return [
            {"时间": stamp, "开盘": 10, "最高": 11, "最低": 9, "收盘": 10}
            for stamp in (
                "2026-10-09T14:25:00+08:00",
                "2026-10-09T06:25:00+00:00",
            )
        ]


class Client:
    def stock_zh_a_hist_min_em(self, **kwargs):
        return Frame()


def test_equal_utc_instants_are_not_double_counted():
    now = datetime(2026, 10, 9, 14, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
    result = AKShareProvider(client=Client(), clock=lambda: now).get_bars(
        "600000", Timeframe.MIN5
    )
    assert result.quality is DataQuality.ERROR
    assert result.value is None
    assert "duplicate bar observation timestamp" in result.error
