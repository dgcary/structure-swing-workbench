"""M4.5 regression tests for duplicate and inconsistent intraday timestamps."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.chip_cost import DayObservation, estimate_distribution
from app.market_data.contracts import Bar, DataQuality


def _bar(timestamp: datetime, price: int, volume: int) -> Bar:
    p = Decimal(price)
    return Bar(
        observed_at=timestamp, open=p, high=p, low=p, close=p,
        volume=Decimal(volume),
    )


def test_duplicate_minute_timestamps_fall_back_to_daily_allocation():
    timestamp = datetime(2026, 10, 12, 2, tzinfo=UTC)
    daily = Bar(
        observed_at=timestamp, open=Decimal(10), high=Decimal(12),
        low=Decimal(10), close=Decimal(11), volume=Decimal(1000),
    )
    # Volumes match exactly, but duplicate timestamps are not a valid series.
    minutes = (_bar(timestamp, 10, 500), _bar(timestamp, 12, 500))
    observation = DayObservation(
        bar=daily, turnover_rate=Decimal(1), floating_shares=Decimal(1000),
        source="fixture", quality=DataQuality.FRESH,
        minute_bars=minutes, corporate_action_checked=True,
    )
    result = estimate_distribution(
        (observation,), bin_width=Decimal(1),
        computed_at=timestamp + timedelta(days=1),
    )
    assert result.estimated_total == Decimal(1000)
    assert result.share_gap == 0
    assert tuple(item.price for item in result.bins) == (
        Decimal(10), Decimal(11), Decimal(12),
    )
    assert "MINUTE_DATA_REJECTED_DAILY_FALLBACK" in result.warnings
    assert "DAILY_UNIFORM_PRICE_APPROXIMATION" in result.warnings
