from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.market_data.akshare_adapter import AKShareProvider
from app.market_data.contracts import (
    Bar, DataQuality, DataResult, MarketDataProvider, Quote, Timeframe,
    moving_average, period_extrema, quality_at,
)

CN = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 10, 9, 14, 30, tzinfo=CN)


class Frame:
    def __init__(self, rows):
        self.rows = rows

    def to_dict(self, orient):
        assert orient == "records"
        return self.rows


class Client:
    def __init__(self):
        self.quote_rows = [{
            "代码": "600000", "名称": "浦发银行", "最新价": 10.5,
            "昨收": 10, "今开": 10.2, "最高": 10.8, "最低": 10.1,
            "涨跌幅": 5, "成交量": 1000, "成交额": 10500,
            "换手率": 1.2, "振幅": 7, "更新时间": "2026-10-09 14:29:00",
        }]
        self.bars = [{
            "日期": "2026-10-08", "时间": "2026-10-09 14:25:00",
            "开盘": 10, "最高": 11, "最低": 9, "收盘": 10.5,
            "成交量": 200, "成交额": 2100,
        }]
        self.periods = []

    def stock_zh_a_spot_em(self):
        return Frame(self.quote_rows)

    def stock_zh_a_hist(self, **kwargs):
        self.periods.append(kwargs)
        return Frame(self.bars)

    def stock_zh_a_hist_min_em(self, **kwargs):
        self.periods.append(kwargs)
        return Frame(self.bars)


    def stock_individual_info_em(self, **kwargs):
        assert kwargs["symbol"] == "600000"
        return Frame([
            {"item": "行业", "value": "银行"},
            {"item": "上市交易所", "value": "上海证券交易所"},
        ])


def provider(client=None):
    return AKShareProvider(client=client or Client(), clock=lambda: NOW)


def test_quote_maps_objective_fields_and_explicit_missing_values():
    result = provider().get_quote("600000")
    assert result.source == "AKShare"
    assert result.quality is DataQuality.FRESH
    assert result.fetched_at == NOW
    assert result.observed_at == datetime(2026, 10, 9, 14, 29, tzinfo=CN)
    assert result.value.last == Decimal("10.5")
    assert result.value.previous_close == Decimal("10")
    assert result.value.close == result.value.last
    assert result.value.limit_up is None
    assert "limit_up" in result.missing_fields
    assert "limit_down" in result.missing_fields


def test_quote_without_source_timestamp_is_unverified_not_live():
    client = Client()
    del client.quote_rows[0]["更新时间"]
    result = provider(client).get_quote("600000")
    assert result.value is not None
    assert result.observed_at is None
    assert result.quality is DataQuality.UNVERIFIED


def test_stale_quote_and_missing_symbol():
    client = Client()
    client.quote_rows[0]["更新时间"] = "2026-10-09 12:00:00"
    assert provider(client).get_quote("600000").quality is DataQuality.STALE
    result = provider(client).get_quote("000001")
    assert result.quality is DataQuality.MISSING
    assert result.value is None


def test_exception_returns_explicit_error():
    class Broken:
        def stock_zh_a_spot_em(self):
            raise RuntimeError("provider offline")

    result = provider(Broken()).get_quote("600000")
    assert result.quality is DataQuality.ERROR
    assert "provider offline" in result.error


@pytest.mark.parametrize("timeframe,method,period", [
    (Timeframe.DAY, "stock_zh_a_hist", "daily"),
    (Timeframe.MIN5, "stock_zh_a_hist_min_em", "5"),
    (Timeframe.MIN15, "stock_zh_a_hist_min_em", "15"),
])
def test_ohlcv_timeframes_are_mapped(timeframe, method, period):
    client = Client()
    result = provider(client).get_bars("600000", timeframe)
    assert result.value[0].close == Decimal("10.5")
    assert result.value[0].volume == Decimal("200")
    assert client.periods[-1]["period"] == period
    assert client.periods[-1]["adjust"] == ""
    assert result.quality is (
        DataQuality.UNVERIFIED if timeframe is Timeframe.DAY else DataQuality.FRESH
    )


def test_bar_invalid_ohlc_returns_error_and_empty_is_missing():
    client = Client()
    client.bars[0]["收盘"] = "bad"
    assert provider(client).get_bars("600000", Timeframe.MIN5).quality is DataQuality.ERROR
    client.bars = []
    assert provider(client).get_bars("600000", Timeframe.DAY).quality is DataQuality.MISSING


def test_security_flags_only_known_facts():
    result = provider().get_security("600000")
    assert result.value.name == "浦发银行"
    assert result.value.is_st is False
    assert result.value.delisting_risk is None
    assert result.value.suspended is None
    assert result.value.industry == "银行"
    assert result.value.exchange == "上海证券交易所"
    assert "delisting_risk" in result.missing_fields


def test_freshness_uses_source_time_not_fetch_time():
    assert quality_at(None, NOW, timedelta(minutes=1)) is DataQuality.UNVERIFIED
    assert quality_at(NOW - timedelta(hours=2), NOW, timedelta(minutes=1)) is DataQuality.STALE
    assert quality_at(NOW + timedelta(hours=1), NOW, timedelta(minutes=1)) is DataQuality.ERROR
    with pytest.raises(ValueError):
        DataResult(
            value=Quote("600000"), source="fake", fetched_at=NOW,
            observed_at=None, quality=DataQuality.FRESH,
        )


def test_provider_is_replaceable_and_math_does_not_predict():
    class FixtureProvider:
        def get_quote(self, symbol):
            return DataResult(
                value=Quote(symbol=symbol, last=Decimal(10)), source="fixture",
                fetched_at=NOW, observed_at=NOW, quality=DataQuality.FRESH,
            )

        def get_bars(self, symbol, timeframe):
            return DataResult(
                value=(), source="fixture", fetched_at=NOW,
                observed_at=NOW, quality=DataQuality.FRESH,
            )

        def get_security(self, symbol):
            return DataResult(
                value=None, source="fixture", fetched_at=NOW,
                observed_at=None, quality=DataQuality.MISSING,
            )

    replacement: MarketDataProvider = FixtureProvider()
    assert replacement.get_quote("600000").value.last == Decimal(10)
    bars = (
        Bar(NOW, Decimal(10), Decimal(12), Decimal(9), Decimal(11)),
        Bar(NOW, Decimal(11), Decimal(13), Decimal(10), Decimal(12)),
    )
    assert moving_average(bars, 2) == Decimal("11.5")
    assert period_extrema(bars, 2) == (Decimal(13), Decimal(9))
    assert moving_average(bars, 3) is None
    with pytest.raises(ValueError):
        period_extrema(bars, 0)


def test_security_detail_failure_is_explicit_and_preserves_partial_quote():
    class NoDetails(Client):
        def stock_individual_info_em(self, **kwargs):
            raise RuntimeError("metadata unavailable")

    result = provider(NoDetails()).get_security("600000")
    assert result.quality is DataQuality.ERROR
    assert result.value.name == "浦发银行"
    assert result.value.industry is None
    assert "industry" in result.missing_fields
    assert "metadata unavailable" in result.error


def test_bar_optional_missing_and_impossible_ohlc_are_explicit():
    client = Client()
    client.bars[0]["成交额"] = None
    result = provider(client).get_bars("600000", Timeframe.MIN5)
    assert result.quality is DataQuality.FRESH
    assert result.value[0].amount is None
    assert "amount" in result.missing_fields

    client.bars[0]["最高"] = 8
    invalid = provider(client).get_bars("600000", Timeframe.MIN5)
    assert invalid.quality is DataQuality.ERROR
    assert "high is below low" in invalid.error
