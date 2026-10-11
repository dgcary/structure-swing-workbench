"""Provider-neutral provenance and freshness boundaries."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.market_data.contracts import DataQuality, DataResult, Quote, quality_at


def test_cross_timezone_observation_uses_absolute_age() -> None:
    fetched = datetime(2026, 10, 11, 7, 0, tzinfo=timezone.utc)
    observed = datetime(2026, 10, 11, 14, 59, tzinfo=timezone(timedelta(hours=8)))
    assert quality_at(observed, fetched, timedelta(minutes=2)) is DataQuality.FRESH
    assert quality_at(observed, fetched, timedelta(seconds=30)) is DataQuality.STALE


def test_fetch_time_does_not_replace_missing_observation_time() -> None:
    fetched = datetime(2026, 10, 11, 7, 0, tzinfo=timezone.utc)
    result = DataResult(
        value=Quote(symbol="000001", last=Decimal("10")),
        source="mock-provider", fetched_at=fetched,
        observed_at=None, quality=DataQuality.UNVERIFIED,
    )
    assert result.source == "mock-provider"
    assert result.fetched_at == fetched
    assert result.observed_at is None
    assert result.quality is DataQuality.UNVERIFIED
    with pytest.raises(ValueError, match="require a source observation timestamp"):
        DataResult(
            value=result.value, source=result.source, fetched_at=fetched,
            observed_at=None, quality=DataQuality.FRESH,
        )


def test_future_observation_beyond_clock_skew_is_error() -> None:
    fetched = datetime(2026, 10, 11, 7, 0, tzinfo=timezone.utc)
    assert quality_at(
        fetched + timedelta(minutes=5, seconds=1), fetched, timedelta(minutes=15)
    ) is DataQuality.ERROR
