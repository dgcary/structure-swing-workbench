from decimal import Decimal

import pytest

from app.position.engine import PositionState, TCycleStatus, TDirection


def state() -> PositionState:
    return PositionState(
        core_quantity=Decimal("700"),
        core_cost=Decimal("10"),
        broker_quantity=Decimal("1000"),
        broker_cost=Decimal("10"),
    )


def test_effective_cost_tracks_realized_t_pnl_without_polluting_core_cost() -> None:
    position = state()
    cycle = position.start_t_cycle(TDirection.POSITIVE, Decimal("100"), Decimal("11"))
    pnl = position.close_t_cycle(cycle, Decimal("100"), Decimal("10.5"))
    assert pnl == Decimal("50.0")
    assert position.core_cost == Decimal("10")
    assert position.realized_t_pnl == Decimal("50.0")
    assert position.effective_cost == Decimal("10") - Decimal("50") / Decimal("700")


def test_partial_fill_counts_only_after_complete_cycle() -> None:
    position = state()
    cycle = position.start_t_cycle(TDirection.REVERSE, Decimal("100"), Decimal("9.8"))
    position.close_t_cycle(cycle, Decimal("40"), Decimal("10.1"))
    assert cycle.status is TCycleStatus.OPEN
    assert cycle.remaining_quantity == Decimal("60")
    assert position.completed_t_cycles_today == 0
    position.close_t_cycle(cycle, Decimal("60"), Decimal("10.2"))
    assert cycle.status is TCycleStatus.CLOSED
    assert position.completed_t_cycles_today == 1


def test_first_two_complete_cycles_allowed_third_rejected() -> None:
    position = state()
    for _ in range(2):
        cycle = position.start_t_cycle(TDirection.REVERSE, Decimal("10"), Decimal("10"))
        position.close_t_cycle(cycle, Decimal("10"), Decimal("10.1"))
    with pytest.raises(ValueError, match="最多2个完整T闭环"):
        position.start_t_cycle(TDirection.REVERSE, Decimal("10"), Decimal("10"))


def test_unclosed_cycle_is_converted_at_day_end_not_counted_as_complete() -> None:
    position = state()
    cycle = position.start_t_cycle(TDirection.REVERSE, Decimal("100"), Decimal("9.8"))
    position.close_t_cycle(cycle, Decimal("40"), Decimal("10"))
    converted = position.convert_open_cycles_at_day_end()
    assert converted == (cycle,)
    assert cycle.status is TCycleStatus.CONVERTED
    assert cycle.remaining_quantity == Decimal("60")
    assert position.completed_t_cycles_today == 0


def test_t_stop_risk_and_reverse_t_exposure_are_objective_math() -> None:
    position = state()
    assert position.t_stop_risk(Decimal("100"), Decimal("10"), Decimal("9.7")) == Decimal("30.0")
    assert position.reverse_t_exposure(Decimal("100"), Decimal("10")) == Decimal("1000")
