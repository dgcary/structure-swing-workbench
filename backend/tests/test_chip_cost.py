"""Fixed-fill replay tests for probabilistic cost distribution, not trade signals."""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.chip_cost import DayObservation, estimate_distribution
from app.market_data.contracts import Bar, DataQuality

D = Decimal
CLOCK = datetime(2026, 10, 12, 16, 0, tzinfo=timezone.utc)


def bar(day: int, price: str, *, low: str | None = None,
        high: str | None = None, volume: str = "1000", hour: int = 0) -> Bar:
    price_value = D(price)
    return Bar(
        observed_at=datetime(2026, 10, day, hour, tzinfo=timezone.utc),
        open=price_value,
        high=D(high) if high is not None else price_value,
        low=D(low) if low is not None else price_value,
        close=price_value,
        volume=D(volume),
    )


def obs(day: int, price: str, *, turnover: str | None = "0.5",
        floating: str | None = "1000", low: str | None = None,
        high: str | None = None, volume: str = "1000",
        minute_bars: tuple[Bar, ...] = (), split: str | None = None,
        checked: bool = True, quality: DataQuality = DataQuality.FRESH,
        source: str = "fixture") -> DayObservation:
    return DayObservation(
        bar=bar(day, price, low=low, high=high, volume=volume),
        turnover_rate=D(turnover) if turnover is not None else None,
        floating_shares=D(floating) if floating is not None else None,
        source=source,
        quality=quality,
        minute_bars=minute_bars,
        split_factor=D(split) if split is not None else None,
        corporate_action_checked=checked,
    )


def by_price(result) -> dict[Decimal, Decimal]:
    return {entry.price: entry.estimated_shares for entry in result.bins}


def test_empty_and_missing_inputs_never_fabricate_costs():
    empty = estimate_distribution((), computed_at=CLOCK)
    assert empty.metrics is None
    assert empty.source_quality is DataQuality.MISSING
    assert empty.warnings == ("EMPTY_HISTORY",)

    missing = estimate_distribution(
        (obs(1, "10", turnover=None),), computed_at=CLOCK,
    )
    assert missing.metrics is None
    assert missing.bins == ()
    assert "INCOMPLETE_OR_UNTRUSTED_HISTORY" in missing.warnings

    error = estimate_distribution(
        (obs(1, "10", quality=DataQuality.ERROR),), computed_at=CLOCK,
    )
    assert error.source_quality is DataQuality.ERROR
    assert error.metrics is None


def test_turnover_decay_and_mean_cost_two_day_replay():
    result = estimate_distribution(
        (obs(1, "10"), obs(2, "12")), computed_at=CLOCK,
    )
    assert by_price(result) == {D("10.0"): D("500"), D("12.0"): D("500")}
    assert result.estimated_total == result.floating_shares == D("1000")
    assert result.share_gap == 0
    assert result.metrics.estimated_mean_cost == D("11.0")
    assert result.metrics.profitable_fraction == D("0.5")
    assert result.metrics.breakeven_fraction == D("0.5")
    assert result.metrics.underwater_fraction == 0
    assert result.metrics.interval_70 == (D("10.0"), D("12.0"))
    assert result.metrics.interval_90 == (D("10.0"), D("12.0"))
    assert sum((item.fraction for item in result.bins), D(0)) == 1
    assert "DAILY_UNIFORM_PRICE_APPROXIMATION" in result.warnings


def test_minute_volume_weights_and_bad_minute_fallback():
    minute = (
        bar(1, "10", volume="750", hour=1),
        bar(1, "12", volume="250", hour=2),
    )
    good = estimate_distribution(
        (obs(1, "10", turnover="1", low="10", high="12", minute_bars=minute),),
        computed_at=CLOCK,
    )
    assert by_price(good) == {D("10.0"): D("750"), D("12.0"): D("250")}
    assert "DAILY_UNIFORM_PRICE_APPROXIMATION" not in good.warnings

    invalid_minute = (bar(1, "10", volume="400", hour=1),)
    fallback = estimate_distribution(
        (obs(1, "10", turnover="1", minute_bars=invalid_minute),),
        computed_at=CLOCK,
    )
    assert by_price(fallback) == {D("10.0"): D("1000")}
    assert "MINUTE_DATA_REJECTED_DAILY_FALLBACK" in fallback.warnings


def test_split_rebases_cost_and_shares_without_inventing_real_holders():
    result = estimate_distribution(
        (
            obs(1, "20", turnover="0", floating="1000"),
            obs(2, "10", turnover="0", floating="2000", split="2"),
        ),
        computed_at=CLOCK,
    )
    assert by_price(result) == {D("10.0"): D("2000")}
    assert result.metrics.estimated_mean_cost == D("10.0")
    assert result.share_gap == 0
    assert "SPLIT_REBASED" in result.warnings
    assert "FLOAT_INCREASE_ESTIMATED_AT_CLOSE" not in result.warnings


def test_float_share_changes_are_explicitly_approximate():
    increase = estimate_distribution(
        (
            obs(1, "10", turnover="0", floating="1000"),
            obs(2, "12", turnover="0", floating="1200"),
        ),
        computed_at=CLOCK,
    )
    assert by_price(increase) == {D("10.0"): D("1000"), D("12.0"): D("200")}
    assert "FLOAT_INCREASE_ESTIMATED_AT_CLOSE" in increase.warnings
    assert increase.share_gap == 0

    decrease = estimate_distribution(
        (
            obs(1, "10", turnover="0", floating="1000"),
            obs(2, "12", turnover="0", floating="500"),
        ),
        computed_at=CLOCK,
    )
    assert by_price(decrease) == {D("10.0"): D("500")}
    assert "FLOAT_DECREASE_PROPORTIONAL_ESTIMATE" in decrease.warnings


def test_history_quality_and_corporate_action_uncertainty_are_preserved():
    result = estimate_distribution(
        (
            obs(1, "10", quality=DataQuality.FRESH),
            obs(2, "11", checked=False, quality=DataQuality.STALE, source="other"),
        ),
        computed_at=CLOCK,
    )
    assert result.source_quality is DataQuality.STALE
    assert result.sources == ("fixture", "other")
    assert result.observed_at == bar(2, "11").observed_at
    assert result.computed_at == CLOCK
    assert "CORPORATE_ACTION_UNVERIFIED" in result.warnings


def test_invalid_input_and_unadjusted_price_contract():
    with pytest.raises(ValueError, match="turnover_rate"):
        obs(1, "10", turnover="1.1")
    with pytest.raises(ValueError, match="floating_shares"):
        obs(1, "10", floating="0")
    with pytest.raises(ValueError, match="split_factor"):
        obs(1, "10", split="-2")
    with pytest.raises(ValueError, match="adjusted prices"):
        DayObservation(
            bar(1, "10"), D("0.5"), D("1000"),
            "fixture", DataQuality.FRESH, price_basis="forward",
        )
    with pytest.raises(ValueError, match="chronological"):
        estimate_distribution((obs(2, "12"), obs(1, "10")), computed_at=CLOCK)
    with pytest.raises(ValueError, match="bin_width"):
        estimate_distribution((obs(1, "10"),), bin_width=D("0"), computed_at=CLOCK)
    with pytest.raises(ValueError, match="timezone"):
        estimate_distribution(
            (obs(1, "10"),), computed_at=datetime(2026, 10, 12),
        )


def test_replay_is_deterministic_and_never_emits_signals():
    history = (
        obs(1, "10", turnover="0.2", low="9.9", high="10.1"),
        obs(2, "10.2", turnover="0.4", low="10.1", high="10.3"),
        obs(3, "10.4", turnover="0.3", low="10.3", high="10.5"),
    )
    first = estimate_distribution(history, computed_at=CLOCK)
    second = estimate_distribution(history, computed_at=CLOCK)
    assert first == second
    assert first.share_gap == 0
    assert first.model_version == "turnover-decay-price-bins-v1"
    assert not hasattr(first, "support")
    assert not hasattr(first, "buy_signal")
    assert first.metrics.interval_70[0] <= first.metrics.interval_70[1]
    assert first.metrics.interval_90[0] <= first.metrics.interval_90[1]



def test_same_day_double_count_is_rejected_even_with_different_timestamps():
    morning = obs(1, "10")
    afternoon = DayObservation(
        bar=bar(1, "11", hour=3),
        turnover_rate=D("0.5"),
        floating_shares=D("1000"),
        source="fixture",
        quality=DataQuality.FRESH,
        corporate_action_checked=True,
    )
    with pytest.raises(ValueError, match="trading date"):
        estimate_distribution((morning, afternoon), computed_at=CLOCK)


def test_impossible_minute_price_reverts_to_daily_range_and_warns():
    # Matching volumes alone must not allow minute prices outside the daily OHLC.
    bad_minute = (
        bar(1, "10", volume="500", hour=1),
        bar(1, "30", volume="500", hour=2),
    )
    result = estimate_distribution(
        (obs(1, "10", turnover="1", minute_bars=bad_minute),),
        computed_at=CLOCK,
    )
    assert by_price(result) == {D("10.0"): D("1000")}
    assert "MINUTE_DATA_REJECTED_DAILY_FALLBACK" in result.warnings
    assert "DAILY_UNIFORM_PRICE_APPROXIMATION" in result.warnings


def test_exchange_date_duplicate_across_utc_midnight_is_rejected():
    from dataclasses import replace

    first = replace(obs(1, "10"), bar=replace(
        bar(1, "10"), observed_at=datetime(2026, 10, 1, 23, tzinfo=timezone.utc),
    ))
    second = replace(obs(2, "11"), bar=replace(
        bar(2, "11"), observed_at=datetime(2026, 10, 2, 1, tzinfo=timezone.utc),
    ))
    with pytest.raises(ValueError, match="trading date"):
        estimate_distribution((first, second), computed_at=CLOCK)


def test_minute_bar_uses_exchange_date_not_utc_date():
    from dataclasses import replace

    daily = replace(bar(1, "10"), observed_at=datetime(
        2026, 10, 1, 23, tzinfo=timezone.utc,
    ))
    minute = replace(bar(2, "10"), observed_at=datetime(
        2026, 10, 2, 1, tzinfo=timezone.utc,
    ))
    item = DayObservation(
        bar=daily, turnover_rate=D("1"), floating_shares=D("1000"),
        source="fixture", quality=DataQuality.FRESH, minute_bars=(minute,),
        corporate_action_checked=True,
    )
    result = estimate_distribution((item,), computed_at=CLOCK)
    assert "MINUTE_DATA_REJECTED_DAILY_FALLBACK" not in result.warnings
    assert "DAILY_UNIFORM_PRICE_APPROXIMATION" not in result.warnings
    assert result.estimated_total == D("1000")
