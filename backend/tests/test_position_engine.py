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


def test_t_fills_update_broker_position_but_keep_core_cost_separate() -> None:
    position = state()
    reverse = position.start_t_cycle(TDirection.REVERSE, Decimal("100"), Decimal("9.8"))
    assert position.broker_quantity == Decimal("1100")
    position.close_t_cycle(reverse, Decimal("100"), Decimal("10.2"))
    assert position.broker_quantity == Decimal("1000")
    assert position.core_quantity == Decimal("700")
    assert position.core_cost == Decimal("10")

    positive = position.start_t_cycle(TDirection.POSITIVE, Decimal("100"), Decimal("11"))
    assert position.broker_quantity == Decimal("900")
    position.close_t_cycle(positive, Decimal("100"), Decimal("10.5"))
    assert position.broker_quantity == Decimal("1000")
    assert position.core_quantity == Decimal("700")
    assert position.core_cost == Decimal("10")


def test_day_end_conversion_reclassifies_without_duplicate_broker_fill() -> None:
    position = state()
    cycle = position.start_t_cycle(TDirection.REVERSE, Decimal("100"), Decimal("9.8"))
    position.close_t_cycle(cycle, Decimal("40"), Decimal("10"))
    assert position.broker_quantity == Decimal("1060")
    position.convert_open_cycles_at_day_end()
    assert position.broker_quantity == Decimal("1060")
    assert position.core_quantity == Decimal("760")


def test_preopened_third_cycle_cannot_bypass_daily_complete_limit() -> None:
    position = state()
    cycles = [
        position.start_t_cycle(TDirection.REVERSE, Decimal("10"), Decimal("10"))
        for _ in range(3)
    ]
    position.close_t_cycle(cycles[0], Decimal("10"), Decimal("10.1"))
    position.close_t_cycle(cycles[1], Decimal("10"), Decimal("10.1"))
    with pytest.raises(ValueError, match="最多2个完整T闭环"):
        position.close_t_cycle(cycles[2], Decimal("10"), Decimal("10.1"))
    assert cycles[2].status is TCycleStatus.OPEN
    assert position.completed_t_cycles_today == 2


def test_multiple_positive_t_cycles_fixed_fill_example() -> None:
    position = state()
    first = position.start_t_cycle(TDirection.POSITIVE, Decimal("100"), Decimal("11.0"))
    assert position.close_t_cycle(first, Decimal("100"), Decimal("10.4")) == Decimal("60.0")
    second = position.start_t_cycle(TDirection.POSITIVE, Decimal("80"), Decimal("10.9"))
    assert position.close_t_cycle(second, Decimal("80"), Decimal("10.5")) == Decimal("32.0")
    assert position.completed_t_cycles_today == 2
    assert position.realized_t_pnl == Decimal("92.0")
    assert position.broker_quantity == Decimal("1000")
    assert position.core_quantity == Decimal("700")
    assert position.core_cost == Decimal("10")


def test_multiple_reverse_t_cycles_fixed_fill_example() -> None:
    position = state()
    first = position.start_t_cycle(TDirection.REVERSE, Decimal("100"), Decimal("9.7"))
    assert position.reverse_t_temporary_exposure == Decimal("970.0")
    assert position.close_t_cycle(first, Decimal("100"), Decimal("10.1")) == Decimal("40.0")
    second = position.start_t_cycle(TDirection.REVERSE, Decimal("50"), Decimal("9.9"))
    assert position.close_t_cycle(second, Decimal("50"), Decimal("10.2")) == Decimal("15.0")
    assert position.completed_t_cycles_today == 2
    assert position.realized_t_pnl == Decimal("55.0")
    assert position.reverse_t_temporary_exposure == Decimal("0")
    assert position.broker_quantity == Decimal("1000")


def test_partial_positive_t_day_end_becomes_ordinary_reduction() -> None:
    position = state()
    cycle = position.start_t_cycle(TDirection.POSITIVE, Decimal("100"), Decimal("11"))
    position.close_t_cycle(cycle, Decimal("40"), Decimal("10.5"))
    assert position.broker_quantity == Decimal("940")
    assert position.realized_t_pnl == Decimal("20.0")
    position.convert_open_cycles_at_day_end()
    assert cycle.status is TCycleStatus.CONVERTED
    assert position.broker_quantity == Decimal("940")
    assert position.core_quantity == Decimal("640")
    assert position.core_cost == Decimal("10")
    assert position.completed_t_cycles_today == 0


def test_target_reduction_and_t_cycle_coexist_without_double_counting() -> None:
    position = state()
    cycle = position.start_t_cycle(TDirection.REVERSE, Decimal("100"), Decimal("9.8"))
    assert position.broker_quantity == Decimal("1100")
    position.apply_target_reduction(Decimal("200"))
    assert position.core_quantity == Decimal("500")
    assert position.broker_quantity == Decimal("900")
    position.close_t_cycle(cycle, Decimal("100"), Decimal("10.2"))
    assert position.broker_quantity == Decimal("800")
    assert position.core_quantity == Decimal("500")
    assert position.realized_t_pnl == Decimal("40.0")
    assert position.core_cost == Decimal("10")
