"""Regression: minute allocation must not create phantom share gaps."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.chip_cost import DayObservation, estimate_distribution
from app.market_data.contracts import Bar, DataQuality


def test_three_equal_minute_volumes_conserve_float_exactly() -> None:
    timestamp = datetime(2026, 10, 12, 2, tzinfo=UTC)
    minute_bars = tuple(
        Bar(
            observed_at=timestamp + timedelta(minutes=offset),
            open=Decimal(price), high=Decimal(price),
            low=Decimal(price), close=Decimal(price), volume=Decimal(1),
        )
        for offset, price in enumerate((10, 11, 12))
    )
    daily = Bar(
        observed_at=timestamp, open=Decimal(10), high=Decimal(12),
        low=Decimal(10), close=Decimal(11), volume=Decimal(3),
    )
    result = estimate_distribution(
        (DayObservation(
            bar=daily, turnover_rate=Decimal(1),
            floating_shares=Decimal(1000), source="fixture",
            quality=DataQuality.FRESH, minute_bars=minute_bars,
            corporate_action_checked=True,
        ),),
        bin_width=Decimal(1),
        computed_at=timestamp + timedelta(days=1),
    )
    assert "MINUTE_DATA_REJECTED_DAILY_FALLBACK" not in result.warnings
    assert "DAILY_UNIFORM_PRICE_APPROXIMATION" not in result.warnings
    assert len(result.bins) == 3
    assert result.estimated_total == Decimal(1000)
    assert result.share_gap == Decimal(0)
    assert sum((item.estimated_shares for item in result.bins), Decimal(0)) == Decimal(1000)
