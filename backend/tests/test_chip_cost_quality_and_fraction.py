"""Regression: source quality and estimated share fractions remain conservative."""
from datetime import UTC, datetime
from decimal import Decimal

from app.chip_cost import DayObservation, estimate_distribution
from app.market_data.contracts import Bar, DataQuality


def _observation(checked: bool, high: str) -> DayObservation:
    return DayObservation(
        bar=Bar(
            observed_at=datetime(2026, 10, 12, 2, tzinfo=UTC),
            open=Decimal("10"), high=Decimal(high), low=Decimal("10"),
            close=Decimal("10"), volume=Decimal("3"),
        ),
        turnover_rate=Decimal("1"),
        floating_shares=Decimal("3"),
        source="fixed-fixture",
        quality=DataQuality.FRESH,
        corporate_action_checked=checked,
    )


def test_unchecked_corporate_actions_downgrade_quality() -> None:
    result = estimate_distribution(
        (_observation(False, "10"),),
        computed_at=datetime(2026, 10, 13, tzinfo=UTC),
    )
    assert result.source_quality is DataQuality.UNVERIFIED
    assert "CORPORATE_ACTION_UNVERIFIED" in result.warnings
    assert result.estimated_total == Decimal("3")


def test_price_bin_fractions_sum_exactly_one() -> None:
    result = estimate_distribution(
        (_observation(True, "12"),),
        bin_width=Decimal("1"),
        computed_at=datetime(2026, 10, 13, tzinfo=UTC),
    )
    assert len(result.bins) == 3
    assert [item.estimated_shares for item in result.bins] == [
        Decimal("1"), Decimal("1"), Decimal("1"),
    ]
    assert sum((item.fraction for item in result.bins), Decimal(0)) == Decimal(1)
    assert result.share_gap == 0
