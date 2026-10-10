"""M4 deterministic validation of invalid market data and bad timeframes."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.market_data.akshare_adapter import AKShareProvider
from app.market_data.contracts import DataQuality, DataResult, Quote, Timeframe

NOW = datetime(2026, 10, 9, 14, 30, tzinfo=ZoneInfo("Asia/Shanghai"))


class Rows:
    def __init__(self, records):
        self.records = records

    def to_dict(self, orient):
        assert orient == "records"
        return self.records


class QuoteClient:
    def __init__(self, override):
        row = {
            "代码": "600000", "名称": "浦发银行", "最新价": 10.5,
            "昨收": 10, "今开": 10.2, "最高": 10.8, "最低": 10.1,
            "成交量": 100, "换手率": 1.2,
            "更新时间": "2026-10-09 14:29:00",
        }
        row.update(override)
        self.row = row

    def stock_zh_a_spot_em(self):
        return Rows([self.row])


@pytest.mark.parametrize("field,value,expected", [
    ("最新价", -1, "quote last is negative"),
    ("最高", 8, "quote high is below low"),
    ("最新价", 12, "quote last is outside high/low"),
    ("成交量", -1, "quote volume is negative"),
    ("换手率", -0.1, "quote turnover_pct is negative"),
    ("涨停价", -1, "quote limit_up is negative"),
    ("跌停价", -1, "quote limit_down is negative"),
    ("成交额", -1, "quote amount is negative"),
])
def test_invalid_quote_is_explicit_error(field, value, expected):
    adapter = AKShareProvider(client=QuoteClient({field: value}), clock=lambda: NOW)
    result = adapter.get_quote("600000")
    assert result.quality is DataQuality.ERROR
    assert result.value is None
    assert expected in result.error


@pytest.mark.parametrize("timeframe", ["5m", "2m", None, 5])
def test_bad_timeframe_returns_error(timeframe):
    adapter = AKShareProvider(client=QuoteClient({}), clock=lambda: NOW)
    result = adapter.get_bars("600000", timeframe)
    assert result.quality is DataQuality.ERROR
    assert result.value is None
    assert result.error == "unsupported timeframe"


class BarClient(QuoteClient):
    def __init__(self, override):
        super().__init__({})
        row = {
            "时间": "2026-10-09 14:25:00",
            "开盘": 10, "最高": 11, "最低": 9, "收盘": 10.5,
            "成交量": 200, "成交额": 2100,
        }
        row.update(override)
        self.bar = row

    def stock_zh_a_hist_min_em(self, **kwargs):
        return Rows([self.bar])


@pytest.mark.parametrize("field,value,expected", [
    ("开盘", -1, "bar open is negative"),
    ("最高", -1, "bar high is negative"),
    ("最低", -1, "bar low is negative"),
    ("收盘", -1, "bar close is negative"),
    ("成交量", -1, "bar volume is negative"),
    ("成交额", -1, "bar amount is negative"),
])
def test_invalid_bar_is_explicit_error(field, value, expected):
    adapter = AKShareProvider(client=BarClient({field: value}), clock=lambda: NOW)
    result = adapter.get_bars("600000", Timeframe.MIN5)
    assert result.quality is DataQuality.ERROR
    assert result.value is None
    assert expected in result.error


def test_inverted_price_limits_return_explicit_error():
    client = QuoteClient({"涨停价": 9, "跌停价": 11})
    result = AKShareProvider(client=client, clock=lambda: NOW).get_quote("600000")
    assert result.quality is DataQuality.ERROR
    assert result.value is None
    assert "limit_down exceeds limit_up" in result.error


def test_duplicate_bar_timestamps_are_rejected_not_double_counted():
    class DuplicateBars(BarClient):
        def stock_zh_a_hist_min_em(self, **kwargs):
            return Rows([self.bar, dict(self.bar)])

    result = AKShareProvider(
        client=DuplicateBars({}), clock=lambda: NOW
    ).get_bars("600000", Timeframe.MIN5)
    assert result.quality is DataQuality.ERROR
    assert result.value is None
    assert "duplicate bar observation timestamp" in result.error


@pytest.mark.parametrize("field,value", [
    ("最新价", "not-a-price"),
    ("成交额", "Infinity"),
    ("换手率", "broken"),
])
def test_malformed_present_quote_number_is_error_not_missing(field, value):
    client = QuoteClient({field: value})
    result = AKShareProvider(client=client, clock=lambda: NOW).get_quote("600000")
    assert result.quality is DataQuality.ERROR
    assert result.value is None
    assert "numeric value" in result.error


def test_explicit_missing_quote_marker_is_not_an_error():
    client = QuoteClient({"成交额": "--", "名称": "NaN"})
    result = AKShareProvider(client=client, clock=lambda: NOW).get_quote("600000")
    assert result.quality is DataQuality.FRESH
    assert result.value.name is None
    assert result.value.amount is None
    assert "name" in result.missing_fields
    assert "amount" in result.missing_fields


def test_malformed_present_bar_number_is_error_not_missing():
    result = AKShareProvider(
        client=BarClient({"成交额": "unparseable"}), clock=lambda: NOW
    ).get_bars("600000", Timeframe.MIN5)
    assert result.quality is DataQuality.ERROR
    assert result.value is None
    assert "invalid numeric value" in result.error


@pytest.mark.parametrize("timestamp", ["yesterday at noon", "2026-99-99 99:99:99"])
def test_malformed_quote_source_timestamp_is_error_not_unverified(timestamp):
    client = QuoteClient({"更新时间": timestamp})
    result = AKShareProvider(client=client, clock=lambda: NOW).get_quote("600000")
    assert result.quality is DataQuality.ERROR
    assert result.value is None
    assert "invalid source timestamp" in result.error


def test_malformed_bar_source_timestamp_is_error_not_unverified():
    result = AKShareProvider(
        client=BarClient({"时间": "2026-10-09 invalid"}), clock=lambda: NOW
    ).get_bars("600000", Timeframe.MIN5)
    assert result.quality is DataQuality.ERROR
    assert result.value is None
    assert "invalid source timestamp" in result.error


@pytest.mark.parametrize("value,quality,observed,reason", [
    (None, DataQuality.FRESH, NOW, "without a value"),
    (None, DataQuality.STALE, NOW, "without a value"),
    (None, DataQuality.UNVERIFIED, None, "without a value"),
    (Quote(symbol="600000"), DataQuality.MISSING, None, "MISSING cannot"),
    (Quote(symbol="600000"), DataQuality.FRESH, None, "FRESH/STALE require"),
    (Quote(symbol="600000"), DataQuality.STALE, None, "FRESH/STALE require"),
])
def test_provider_neutral_result_rejects_contradictory_quality(
    value, quality, observed, reason,
):
    with pytest.raises(ValueError, match=reason):
        DataResult(
            value=value, source="fixture", fetched_at=NOW,
            observed_at=observed, quality=quality,
        )


def test_provider_neutral_result_allows_explicit_missing_and_unverified():
    missing = DataResult(
        value=None, source="fixture", fetched_at=NOW,
        observed_at=None, quality=DataQuality.MISSING,
    )
    unverified = DataResult(
        value=Quote(symbol="600000"), source="fixture", fetched_at=NOW,
        observed_at=None, quality=DataQuality.UNVERIFIED,
    )
    assert missing.quality is DataQuality.MISSING
    assert unverified.quality is DataQuality.UNVERIFIED


@pytest.mark.parametrize("other_last", [10.5, 10.6])
def test_duplicate_quote_rows_are_rejected_even_when_identical(other_last):
    class DuplicateQuotes(QuoteClient):
        def stock_zh_a_spot_em(self):
            second = dict(self.row)
            second["最新价"] = other_last
            return Rows([self.row, second])

    result = AKShareProvider(
        client=DuplicateQuotes({}), clock=lambda: NOW
    ).get_quote("600000")
    assert result.quality is DataQuality.ERROR
    assert result.value is None
    assert "duplicate quote rows for symbol" in result.error
