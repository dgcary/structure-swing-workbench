"""Bound price-bin expansion for adversarial or malformed ranges."""
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.chip_cost import DayObservation, estimate_distribution
from app.market_data.contracts import Bar, DataQuality


def test_oversized_price_range_requires_wider_bin() -> None:
    bar = Bar(
        observed_at=datetime(2026, 10, 12, tzinfo=UTC),
        open=Decimal("10"),
        high=Decimal("3000"),
        low=Decimal("1"),
        close=Decimal("10"),
        volume=Decimal("1000"),
    )
    observation = DayObservation(
        bar=bar,
        turnover_rate=Decimal("1"),
        floating_shares=Decimal("1000"),
        source="fixture",
        quality=DataQuality.FRESH,
        corporate_action_checked=True,
    )
    with pytest.raises(ValueError, match="20000 bins"):
        estimate_distribution((observation,), computed_at=datetime(2026, 10, 13, tzinfo=UTC))

    valid = estimate_distribution(
        (observation,), bin_width=Decimal("1"),
        computed_at=datetime(2026, 10, 13, tzinfo=UTC),
    )
    assert valid.estimated_total == Decimal("1000")
    assert valid.share_gap == 0
