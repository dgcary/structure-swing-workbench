"""M4 regression tests for pandas nullable scalar missing markers."""
from datetime import datetime
from zoneinfo import ZoneInfo

from app.market_data.akshare_adapter import AKShareProvider
from app.market_data.contracts import DataQuality, Timeframe

NOW = datetime(2026, 10, 9, 14, 30, tzinfo=ZoneInfo("Asia/Shanghai"))


class NullableScalar:
    """Emulates the textual representation of pandas.NA without pandas."""

    def __str__(self):
        return "<NA>"


class Rows:
    def __init__(self, records):
        self.records = records

    def to_dict(self, orient):
        assert orient == "records"
        return self.records


class NullableClient:
    def stock_zh_a_spot_em(self):
        return Rows([{
            "代码": "600000", "名称": "浦发银行",
            "最新价": 10, "今开": 10, "最高": 10, "最低": 10,
            "成交额": NullableScalar(),
            "更新时间": NullableScalar(), "时间": "2026-10-09 14:29:00",
        }])

    def stock_zh_a_hist_min_em(self, **kwargs):
        return Rows([{
            "时间": NullableScalar(), "日期": "2026-10-09 14:25:00",
            "开盘": 10, "最高": 10, "最低": 10, "收盘": 10,
            "成交量": NullableScalar(),
        }])

    def stock_individual_info_em(self, **kwargs):
        return Rows([
            {"item": "行业", "value": NullableScalar()},
            {"item": "交易所", "value": NullableScalar()},
            {"item": "上市交易所", "value": "上海证券交易所"},
        ])


def test_nullable_quote_number_is_missing_and_source_time_falls_back():
    result = AKShareProvider(client=NullableClient(), clock=lambda: NOW).get_quote("600000")
    assert result.quality is DataQuality.FRESH
    assert result.value.amount is None
    assert "amount" in result.missing_fields
    assert result.observed_at.minute == 29


def test_nullable_minute_bar_volume_is_missing_and_time_falls_back():
    result = AKShareProvider(client=NullableClient(), clock=lambda: NOW).get_bars(
        "600000", Timeframe.MIN5
    )
    assert result.quality is DataQuality.FRESH
    assert result.value[0].volume is None
    assert "volume" in result.missing_fields
    assert result.value[0].observed_at.minute == 25


def test_nullable_metadata_never_becomes_literal_industry():
    result = AKShareProvider(client=NullableClient(), clock=lambda: NOW).get_security("600000")
    assert result.quality is DataQuality.UNVERIFIED
    assert result.value.industry is None
    assert result.value.exchange == "上海证券交易所"
    assert "industry" in result.missing_fields
