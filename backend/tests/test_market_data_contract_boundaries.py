"""Deterministic boundary coverage for provider-neutral market-data contracts."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.market_data.contracts import (
    Bar,
    DataQuality,
    DataResult,
    Quote,
    moving_average,
    period_extrema,
    quality_at,
)

NOW = datetime(2026, 10, 9, 14, 30, tzinfo=UTC)


def test_source_freshness_threshold_is_inclusive():
    assert quality_at(NOW - timedelta(minutes=15), NOW, timedelta(minutes=15)) is DataQuality.FRESH
    assert (
        quality_at(NOW - timedelta(minutes=15, seconds=1), NOW, timedelta(minutes=15))
        is DataQuality.STALE
    )


def test_future_source_timestamp_exceeding_tolerance_is_error():
    assert quality_at(NOW + timedelta(minutes=5), NOW, timedelta(minutes=1)) is DataQuality.FRESH
    assert (
        quality_at(NOW + timedelta(minutes=5, seconds=1), NOW, timedelta(minutes=1))
        is DataQuality.ERROR
    )


def test_source_quality_rejects_negative_age_limit_and_naive_times():
    with pytest.raises(ValueError):
        quality_at(NOW, NOW, timedelta(seconds=-1))
    with pytest.raises(ValueError):
        quality_at(NOW.replace(tzinfo=None), NOW, timedelta(minutes=1))
    with pytest.raises(ValueError):
        quality_at(NOW, NOW.replace(tzinfo=None), timedelta(minutes=1))


def test_result_rejects_naive_observation_or_fetch_time():
    with pytest.raises(ValueError):
        DataResult(
            value=Quote(symbol="600000"), source="fixture",
            fetched_at=NOW.replace(tzinfo=None),
            observed_at=NOW, quality=DataQuality.FRESH,
        )
    with pytest.raises(ValueError):
        DataResult(
            value=Quote(symbol="600000"), source="fixture",
            fetched_at=NOW,
            observed_at=NOW.replace(tzinfo=None), quality=DataQuality.FRESH,
        )


def test_math_returns_none_when_window_is_too_large_and_rejects_zero():
    bars = (
        Bar(NOW, Decimal(10), Decimal(12), Decimal(9), Decimal(11)),
        Bar(NOW, Decimal(11), Decimal(13), Decimal(10), Decimal(12)),
    )
    assert moving_average(bars, 3) is None
    assert period_extrema(bars, 3) is None
    with pytest.raises(ValueError):
        moving_average(bars, 0)
    with pytest.raises(ValueError):
        period_extrema(bars, -1)
