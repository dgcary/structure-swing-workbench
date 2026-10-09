"""Fixed-fill regressions for split opening fills of one logical T cycle."""

from decimal import Decimal

import pytest

from app.position.engine import PositionState, TCycleStatus, TDirection


def position() -> PositionState:
    return PositionState(Decimal(700), Decimal(10), Decimal(1000), Decimal(10))


def test_split_reverse_open_fills_use_weighted_entry_and_one_cycle() -> None:
    p = position()
    cycle = p.start_t_cycle(TDirection.REVERSE, Decimal(40), Decimal("9.5"))
    p.add_t_open_fill(cycle, Decimal(60), Decimal("10.5"))
    assert cycle.open_quantity == Decimal(100)
    assert cycle.open_price == Decimal("10.1")
    assert p.broker_quantity == Decimal(1100)
    assert p.same_day_buy_quantity == Decimal(100)
    assert p.reverse_t_temporary_exposure == Decimal(1010)

    assert p.close_t_cycle(cycle, Decimal(100), Decimal(11)) == Decimal(90)
    assert cycle.status is TCycleStatus.CLOSED
    assert p.completed_t_cycles_today == 1
    assert p.broker_quantity == Decimal(1000)
    assert p.core_quantity == Decimal(700)
    assert p.core_cost == Decimal(10)


def test_split_positive_open_fills_and_partial_buybacks_count_once() -> None:
    p = position()
    cycle = p.start_t_cycle(TDirection.POSITIVE, Decimal(40), Decimal(11))
    p.add_t_open_fill(cycle, Decimal(60), Decimal(12))
    assert cycle.open_price == Decimal("11.6")
    assert p.broker_quantity == Decimal(900)

    assert p.close_t_cycle(cycle, Decimal(40), Decimal("10.5")) == Decimal(44)
    assert p.completed_t_cycles_today == 0
    assert p.close_t_cycle(cycle, Decimal(60), Decimal(10)) == Decimal(96)
    assert p.realized_t_pnl == Decimal(140)
    assert p.completed_t_cycles_today == 1
    assert p.broker_quantity == Decimal(1000)
    assert p.core_cost == Decimal(10)


def test_cannot_append_open_fill_after_partial_close() -> None:
    p = position()
    cycle = p.start_t_cycle(TDirection.REVERSE, Decimal(20), Decimal(10))
    p.close_t_cycle(cycle, Decimal(10), Decimal(11))
    before = (cycle.open_quantity, p.broker_quantity, p.realized_t_pnl)
    with pytest.raises(ValueError, match="闭环成交前"):
        p.add_t_open_fill(cycle, Decimal(10), Decimal(10))
    assert (cycle.open_quantity, p.broker_quantity, p.realized_t_pnl) == before


def test_rejected_split_open_fill_does_not_mutate_inventory() -> None:
    p = position()
    cycle = p.start_t_cycle(TDirection.POSITIVE, Decimal(250), Decimal(11))
    before = (cycle.open_quantity, cycle.open_price, p.broker_quantity)
    with pytest.raises(ValueError, match="不得侵蚀核心仓"):
        p.add_t_open_fill(cycle, Decimal(60), Decimal(11))
    assert (cycle.open_quantity, cycle.open_price, p.broker_quantity) == before
