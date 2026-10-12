"""Regression: zero-turnover days do not imply any price allocation."""
from datetime import UTC, datetime
from decimal import Decimal

from app.chip_cost import DayObservation, estimate_distribution
from app.market_data.contracts import Bar, DataQuality


def test_zero_turnover_does_not_allocate_buckets_or_emit_approximation():
    # The daily price range spans >20,000 buckets at width 0.1.
    # A day with no turnover must not attempt to distribute zero shares.
    observed_at = datetime(2026, 10, 12, tzinfo=UTC)
    daily = Bar(
        observed_at=observed_at,
        open=Decimal(10),
        high=Decimal(3000),
        low=Decimal(1),
        close=Decimal(10),
        volume=Decimal(0),
    )
    item = DayObservation(
        bar=daily,
        turnover_rate=Decimal(0),
        floating_shares=Decimal(1000),
        source="fixture",
        quality=DataQuality.FRESH,
        corporate_action_checked=True,
    )
    result = estimate_distribution(
        (item,),
        computed_at=datetime(2026, 10, 13, tzinfo=UTC),
    )
    assert result.estimated_total == Decimal(1000)
    assert result.metrics.estimated_mean_cost == Decimal(10)
    assert len(result.bins) == 1
    assert "DAILY_UNIFORM_PRICE_APPROXIMATION" not in result.warnings
    assert "MINUTE_DATA_REJECTED_DAILY_FALLBACK" not in result.warnings
