"""Regression tests for M3 execution fills and trading-day boundaries."""

from datetime import date
from decimal import Decimal

import pytest

from app.position.engine import PositionState, TCycleStatus, TDirection


def position() -> PositionState:
    return PositionState(
        core_quantity=Decimal(700),
        core_cost=Decimal(10),
        broker_quantity=Decimal(1000),
        broker_cost=Decimal(10),
    )


def test_split_positive_open_fills_use_weighted_price_and_one_cycle() -> None:
    state = position()
    cycle = state.start_t_cycle(TDirection.POSITIVE, Decimal(50), Decimal(11))
    state.add_t_open_fill(cycle, Decimal(50), Decimal(10))
    assert cycle.open_quantity == Decimal(100)
    assert cycle.open_price == Decimal("10.5")
    assert state.broker_quantity == Decimal(900)

    assert state.close_t_cycle(cycle, Decimal(40), Decimal("10.2")) == Decimal("12.0")
    assert cycle.status is TCycleStatus.OPEN
    assert state.completed_t_cycles_today == 0
    assert state.close_t_cycle(cycle, Decimal(60), Decimal("10.2")) == Decimal("18.0")
    assert cycle.status is TCycleStatus.CLOSED
    assert state.completed_t_cycles_today == 1
    assert state.realized_t_pnl == Decimal("30.0")
    assert state.broker_quantity == Decimal(1000)
    assert state.core_quantity == Decimal(700)
    assert state.core_cost == Decimal(10)


def test_split_reverse_open_fills_keep_t_plus_one_inventory_and_exposure() -> None:
    state = position()
    cycle = state.start_t_cycle(TDirection.REVERSE, Decimal(50), Decimal("9.8"))
    state.add_t_open_fill(cycle, Decimal(50), Decimal("10.2"))
    assert cycle.open_price == Decimal(10)
    assert state.broker_quantity == Decimal(1100)
    assert state.same_day_buy_quantity == Decimal(100)
    assert state.old_sellable_quantity == Decimal(1000)
    assert state.reverse_t_temporary_exposure == Decimal(1000)
    assert state.total_market_exposure(Decimal(10)) == Decimal(11000)

    assert state.close_t_cycle(cycle, Decimal(40), Decimal("10.5")) == Decimal("20.0")
    assert state.old_sellable_quantity == Decimal(960)
    assert state.reverse_t_temporary_exposure == Decimal(600)
    assert state.close_t_cycle(cycle, Decimal(60), Decimal("10.4")) == Decimal("24.0")
    assert state.completed_t_cycles_today == 1
    assert state.realized_t_pnl == Decimal("44.0")
    assert state.broker_quantity == Decimal(1000)
    assert state.core_quantity == Decimal(700)


def test_next_trading_day_resets_quota_and_unlocks_prior_buys() -> None:
    state = position()
    assert state.advance_trading_day(date(2026, 10, 8)) == ()
    for _ in range(2):
        cycle = state.start_t_cycle(TDirection.POSITIVE, Decimal(50), Decimal(11))
        state.close_t_cycle(cycle, Decimal(50), Decimal("10.5"))
    assert state.completed_t_cycles_today == 2
    assert state.same_day_buy_quantity == Decimal(100)
    assert state.old_sellable_quantity == Decimal(900)

    assert state.advance_trading_day(date(2026, 10, 8)) == ()
    assert state.completed_t_cycles_today == 2
    assert state.advance_trading_day(date(2026, 10, 9)) == ()
    assert state.completed_t_cycles_today == 0
    assert state.same_day_buy_quantity == Decimal(0)
    assert state.old_sellable_quantity == Decimal(1000)
    cycle = state.start_t_cycle(TDirection.POSITIVE, Decimal(100), Decimal(11))
    assert cycle.status is TCycleStatus.OPEN


def test_day_end_failed_inventory_preflight_is_atomic() -> None:
    state = position()
    cycle = state.start_t_cycle(TDirection.REVERSE, Decimal(100), Decimal("9.8"))
    # Simulate a broker-side adjustment not classified by the strategy.
    state.apply_broker_sell(Decimal(350))
    before = (
        state.core_quantity,
        state.core_cost,
        state.broker_quantity,
        state.ordinary_t_addition_quantity,
        state.ordinary_t_reduction_quantity,
    )
    with pytest.raises(ValueError, match="超过券商持仓"):
        state.convert_open_cycles_at_day_end()
    assert cycle.status is TCycleStatus.OPEN
    assert cycle.remaining_quantity == Decimal(100)
    assert (
        state.core_quantity,
        state.core_cost,
        state.broker_quantity,
        state.ordinary_t_addition_quantity,
        state.ordinary_t_reduction_quantity,
    ) == before
