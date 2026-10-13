"""M4.5: minute-volume tolerance is inclusive and never hides a fallback."""
from datetime import UTC, datetime
from decimal import Decimal

from app.chip_cost import DayObservation, estimate_distribution
from app.market_data.contracts import Bar, DataQuality


def _bar(timestamp: datetime, price: int, volume: int) -> Bar:
    value = Decimal(price)
    return Bar(
        observed_at=timestamp,
        open=value, high=value, low=value, close=value,
        volume=Decimal(volume),
    )


def test_minute_volume_tolerance_boundary_is_explicit() -> None:
    timestamp = datetime(2026, 10, 12, 2, tzinfo=UTC)
    daily = Bar(
        observed_at=timestamp, open=Decimal(11),
        high=Decimal(12), low=Decimal(10), close=Decimal(11),
        volume=Decimal(1000),
    )

    def replay(minute_volume: int):
        observation = DayObservation(
            bar=daily,
            turnover_rate=Decimal(1),
            floating_shares=Decimal(1000),
            source="fixture",
            quality=DataQuality.FRESH,
            minute_bars=(_bar(timestamp, 10, minute_volume),),
            corporate_action_checked=True,
        )
        return estimate_distribution(
            (observation,), bin_width=Decimal(1),
            computed_at=datetime(2026, 10, 13, tzinfo=UTC),
        )

    within = replay(1010)  # exactly +1%: accepted
    assert tuple(item.price for item in within.bins) == (Decimal(10),)
    assert "MINUTE_DATA_REJECTED_DAILY_FALLBACK" not in within.warnings
    assert within.share_gap == 0

    outside = replay(1011)  # above +1%: daily fallback
    assert tuple(item.price for item in outside.bins) == (
        Decimal(10), Decimal(11), Decimal(12),
    )
    assert "MINUTE_DATA_REJECTED_DAILY_FALLBACK" in outside.warnings
    assert "DAILY_UNIFORM_PRICE_APPROXIMATION" in outside.warnings
    assert outside.share_gap == 0
