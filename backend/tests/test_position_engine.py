from datetime import date
from decimal import Decimal

import pytest

from app.position.engine import (
    BrokerInventoryConflict,
    CoreBuyAction,
    PositionState,
    TCycleStatus,
    TDirection,
)


def state() -> PositionState:
    return PositionState(
        core_quantity=Decimal(700),
        core_cost=Decimal(10),
        broker_quantity=Decimal(1000),
        broker_cost=Decimal(10),
    )


def test_effective_cost_tracks_realized_t_pnl_without_polluting_core_cost() -> None:
    position = state()
    cycle = position.start_t_cycle(TDirection.POSITIVE, Decimal(100), Decimal(11))
    pnl = position.close_t_cycle(cycle, Decimal(100), Decimal("10.5"))
    assert pnl == Decimal("50.0")
    assert position.core_cost == Decimal(10)
    assert position.realized_t_pnl == Decimal("50.0")
    assert position.effective_cost == Decimal(10) - Decimal(50) / Decimal(700)


def test_partial_fill_counts_only_after_complete_cycle() -> None:
    position = state()
    cycle = position.start_t_cycle(TDirection.REVERSE, Decimal(100), Decimal("9.8"))
    position.close_t_cycle(cycle, Decimal(40), Decimal("10.1"))
    assert cycle.status is TCycleStatus.OPEN
    assert cycle.remaining_quantity == Decimal(60)
    assert position.completed_t_cycles_today == 0
    position.close_t_cycle(cycle, Decimal(60), Decimal("10.2"))
    assert cycle.status is TCycleStatus.CLOSED
    assert position.completed_t_cycles_today == 1


def test_first_two_complete_cycles_allowed_third_rejected() -> None:
    position = state()
    for _ in range(2):
        cycle = position.start_t_cycle(TDirection.REVERSE, Decimal(10), Decimal(10))
        position.close_t_cycle(cycle, Decimal(10), Decimal("10.1"))
    with pytest.raises(ValueError, match="最多2个完整T闭环"):
        position.start_t_cycle(TDirection.REVERSE, Decimal(10), Decimal(10))


def test_unclosed_cycle_is_converted_at_day_end_not_counted_as_complete() -> None:
    position = state()
    cycle = position.start_t_cycle(TDirection.REVERSE, Decimal(100), Decimal("9.8"))
    position.close_t_cycle(cycle, Decimal(40), Decimal(10))
    converted = position.convert_open_cycles_at_day_end()
    assert converted == (cycle,)
    assert cycle.status is TCycleStatus.CONVERTED
    assert cycle.remaining_quantity == Decimal(60)
    assert position.completed_t_cycles_today == 0


def test_t_stop_risk_and_reverse_t_exposure_are_objective_math() -> None:
    position = state()
    assert position.t_stop_risk(Decimal(100), Decimal(10), Decimal("9.7")) == Decimal("30.0")
    assert position.reverse_t_exposure(Decimal(100), Decimal(10)) == Decimal(1000)


def test_t_fills_update_broker_position_but_keep_core_cost_separate() -> None:
    position = state()
    reverse = position.start_t_cycle(TDirection.REVERSE, Decimal(100), Decimal("9.8"))
    assert position.broker_quantity == Decimal(1100)
    position.close_t_cycle(reverse, Decimal(100), Decimal("10.2"))
    assert position.broker_quantity == Decimal(1000)
    assert position.core_quantity == Decimal(700)
    assert position.core_cost == Decimal(10)

    positive = position.start_t_cycle(TDirection.POSITIVE, Decimal(100), Decimal(11))
    assert position.broker_quantity == Decimal(900)
    position.close_t_cycle(positive, Decimal(100), Decimal("10.5"))
    assert position.broker_quantity == Decimal(1000)
    assert position.core_quantity == Decimal(700)
    assert position.core_cost == Decimal(10)


def test_day_end_conversion_reclassifies_without_duplicate_broker_fill() -> None:
    position = state()
    cycle = position.start_t_cycle(TDirection.REVERSE, Decimal(100), Decimal("9.8"))
    position.close_t_cycle(cycle, Decimal(40), Decimal(10))
    assert position.broker_quantity == Decimal(1060)
    position.convert_open_cycles_at_day_end()
    assert position.broker_quantity == Decimal(1060)
    assert position.core_quantity == Decimal(760)


def test_preopened_third_cycle_cannot_bypass_daily_complete_limit() -> None:
    position = state()
    cycles = [
        position.start_t_cycle(TDirection.REVERSE, Decimal(10), Decimal(10))
        for _ in range(3)
    ]
    position.close_t_cycle(cycles[0], Decimal(10), Decimal("10.1"))
    position.close_t_cycle(cycles[1], Decimal(10), Decimal("10.1"))
    with pytest.raises(ValueError, match="最多2个完整T闭环"):
        position.close_t_cycle(cycles[2], Decimal(10), Decimal("10.1"))
    assert cycles[2].status is TCycleStatus.OPEN
    assert position.completed_t_cycles_today == 2


def test_multiple_positive_t_cycles_fixed_fill_example() -> None:
    position = state()
    first = position.start_t_cycle(TDirection.POSITIVE, Decimal(100), Decimal("11.0"))
    assert position.close_t_cycle(first, Decimal(100), Decimal("10.4")) == Decimal("60.0")
    second = position.start_t_cycle(TDirection.POSITIVE, Decimal(80), Decimal("10.9"))
    assert position.close_t_cycle(second, Decimal(80), Decimal("10.5")) == Decimal("32.0")
    assert position.completed_t_cycles_today == 2
    assert position.realized_t_pnl == Decimal("92.0")
    assert position.broker_quantity == Decimal(1000)
    assert position.core_quantity == Decimal(700)
    assert position.core_cost == Decimal(10)


def test_multiple_reverse_t_cycles_fixed_fill_example() -> None:
    position = state()
    first = position.start_t_cycle(TDirection.REVERSE, Decimal(100), Decimal("9.7"))
    assert position.reverse_t_temporary_exposure == Decimal("970.0")
    assert position.close_t_cycle(first, Decimal(100), Decimal("10.1")) == Decimal("40.0")
    second = position.start_t_cycle(TDirection.REVERSE, Decimal(50), Decimal("9.9"))
    assert position.close_t_cycle(second, Decimal(50), Decimal("10.2")) == Decimal("15.0")
    assert position.completed_t_cycles_today == 2
    assert position.realized_t_pnl == Decimal("55.0")
    assert position.reverse_t_temporary_exposure == Decimal(0)
    assert position.broker_quantity == Decimal(1000)


def test_partial_positive_t_day_end_becomes_ordinary_reduction() -> None:
    position = state()
    cycle = position.start_t_cycle(TDirection.POSITIVE, Decimal(100), Decimal(11))
    position.close_t_cycle(cycle, Decimal(40), Decimal("10.5"))
    assert position.broker_quantity == Decimal(940)
    assert position.realized_t_pnl == Decimal(0)
    assert position.pending_t_pnl == Decimal("20.0")
    position.convert_open_cycles_at_day_end()
    assert position.pending_t_pnl == Decimal(0)
    assert position.converted_t_pnl == Decimal("20.0")
    assert cycle.status is TCycleStatus.CONVERTED
    assert position.broker_quantity == Decimal(940)
    assert position.core_quantity == Decimal(700)
    assert position.ordinary_t_reduction_quantity == Decimal(60)
    assert position.core_cost == Decimal(10)
    assert position.completed_t_cycles_today == 0


def test_target_reduction_and_t_cycle_coexist_without_double_counting() -> None:
    position = state()
    cycle = position.start_t_cycle(TDirection.REVERSE, Decimal(100), Decimal("9.8"))
    assert position.broker_quantity == Decimal(1100)
    position.apply_target_reduction(Decimal(200))
    assert position.core_quantity == Decimal(500)
    assert position.broker_quantity == Decimal(900)
    position.close_t_cycle(cycle, Decimal(100), Decimal("10.2"))
    assert position.broker_quantity == Decimal(800)
    assert position.core_quantity == Decimal(500)
    assert position.realized_t_pnl == Decimal("40.0")
    assert position.core_cost == Decimal(10)


def test_zero_remaining_reverse_exposure_is_decimal_zero() -> None:
    position = state()
    cycle = position.start_t_cycle(TDirection.REVERSE, Decimal(10), Decimal("9.8"))
    position.close_t_cycle(cycle, Decimal(10), Decimal(10))
    assert position.reverse_t_temporary_exposure == Decimal(0)


def test_reverse_t_cannot_use_core_inventory_as_old_sellable_position() -> None:
    position = PositionState(
        core_quantity=Decimal(700),
        core_cost=Decimal(10),
        broker_quantity=Decimal(700),
        broker_cost=Decimal(10),
    )
    with pytest.raises(ValueError, match="不得侵蚀核心仓"):
        position.start_t_cycle(TDirection.REVERSE, Decimal(100), Decimal("9.8"))


def test_large_target_reduction_keeps_open_reverse_t_separately_closeable() -> None:
    position = PositionState(
        core_quantity=Decimal(700),
        core_cost=Decimal(10),
        broker_quantity=Decimal(1000),
        broker_cost=Decimal(10),
    )
    cycle = position.start_t_cycle(TDirection.REVERSE, Decimal(100), Decimal("9.8"))
    position.apply_target_reduction(Decimal(650))
    assert position.core_quantity == Decimal(50)
    assert position.broker_quantity == Decimal(450)
    position.close_t_cycle(cycle, Decimal(100), Decimal("10.2"))
    assert position.core_quantity == Decimal(50)
    assert position.broker_quantity == Decimal(350)


def test_t_cycle_rejects_non_positive_prices_without_mutating_position() -> None:
    position = state()
    with pytest.raises(ValueError, match="成交价格必须大于0"):
        position.start_t_cycle(TDirection.REVERSE, Decimal(10), Decimal(0))
    assert position.broker_quantity == Decimal(1000)
    assert position.t_cycles == []

    cycle = position.start_t_cycle(TDirection.REVERSE, Decimal(10), Decimal("9.8"))
    with pytest.raises(ValueError, match="成交价格必须大于0"):
        position.close_t_cycle(cycle, Decimal(10), Decimal(0))
    assert cycle.status is TCycleStatus.OPEN
    assert cycle.remaining_quantity == Decimal(10)
    assert position.completed_t_cycles_today == 0


def test_objective_risk_math_rejects_negative_inputs() -> None:
    position = state()
    with pytest.raises(ValueError, match="不得为负"):
        position.reverse_t_exposure(Decimal(-1), Decimal(10))
    with pytest.raises(ValueError, match="不得为负"):
        position.t_stop_risk(Decimal(10), Decimal(-1), Decimal(9))


def test_positive_t_cannot_reuse_open_reverse_t_temporary_inventory() -> None:
    position = state()
    reverse = position.start_t_cycle(TDirection.REVERSE, Decimal(100), Decimal("9.8"))
    assert position.broker_quantity == Decimal(1100)

    with pytest.raises(ValueError, match="T仓不得侵蚀核心仓"):
        position.start_t_cycle(TDirection.POSITIVE, Decimal(201), Decimal("10.5"))

    positive = position.start_t_cycle(TDirection.POSITIVE, Decimal(200), Decimal("10.5"))
    assert position.broker_quantity == Decimal(900)
    position.close_t_cycle(positive, Decimal(200), Decimal("10.2"))
    position.close_t_cycle(reverse, Decimal(100), Decimal("10.1"))
    assert position.broker_quantity == Decimal(1000)
    assert position.core_quantity == Decimal(700)


def test_multiple_unclosed_positive_cycles_are_noncore_reductions() -> None:
    position = state()
    position.start_t_cycle(TDirection.POSITIVE, Decimal(100), Decimal(11))
    position.start_t_cycle(TDirection.POSITIVE, Decimal(200), Decimal("10.8"))
    converted = position.convert_open_cycles_at_day_end()
    assert len(converted) == 2
    assert position.broker_quantity == Decimal(700)
    assert position.core_quantity == Decimal(700)
    assert position.ordinary_t_reduction_quantity == Decimal(300)
    assert position.convert_open_cycles_at_day_end() == ()
    assert position.ordinary_t_reduction_quantity == Decimal(300)


def test_unclosed_reverse_is_recorded_as_ordinary_addition_once() -> None:
    position = state()
    position.start_t_cycle(TDirection.REVERSE, Decimal(100), Decimal("9.8"))
    position.convert_open_cycles_at_day_end()
    assert position.core_quantity == Decimal(800)
    assert position.ordinary_t_addition_quantity == Decimal(100)
    assert position.convert_open_cycles_at_day_end() == ()
    assert position.ordinary_t_addition_quantity == Decimal(100)


def test_third_preopened_cycle_cannot_partially_match_after_limit() -> None:
    position = state()
    cycles = [position.start_t_cycle(TDirection.REVERSE, Decimal(10), Decimal(10))
              for _ in range(3)]
    for cycle in cycles[:2]:
        position.close_t_cycle(cycle, Decimal(10), Decimal("10.2"))
    before = (position.realized_t_pnl, position.broker_quantity)
    with pytest.raises(ValueError, match="最多2个完整T闭环"):
        position.close_t_cycle(cycles[2], Decimal(1), Decimal("10.2"))
    assert cycles[2].matched_quantity == Decimal(0)
    assert (position.realized_t_pnl, position.broker_quantity) == before


def test_broker_display_cost_is_external_and_reconciliation_is_atomic() -> None:
    position = state()
    position.set_broker_display_cost(Decimal("8.5"))
    position.apply_core_buy(Decimal(20), Decimal(12), CoreBuyAction.ADD)
    assert position.broker_quantity == Decimal(1020)
    assert position.broker_display_cost == Decimal("8.5")
    assert position.broker_cost == Decimal("8.5")
    estimate = (Decimal(1000) * 10 + Decimal(20) * 12) / Decimal(1020)
    assert position.estimated_broker_cost == estimate
    with pytest.raises(BrokerInventoryConflict, match="数量不一致"):
        position.reconcile_broker_cost(Decimal(1000), Decimal("7.1"))
    assert position.broker_display_cost == Decimal("8.5")
    position.reconcile_broker_cost(Decimal(1020), Decimal("-1.2"))
    assert position.broker_display_cost == Decimal("-1.2")
    assert position.estimated_broker_cost == estimate


def test_core_initial_and_add_split_fills_update_both_ledgers_and_t_plus_one() -> None:
    position = PositionState(
        core_quantity=Decimal(0),
        core_cost=Decimal(0),
        broker_quantity=Decimal(0),
        broker_cost=Decimal(0),
        trading_day=date(2026, 10, 8),
    )
    position.apply_core_buy(Decimal(40), Decimal(10), CoreBuyAction.BUY_INITIAL)
    position.apply_core_buy(Decimal(60), Decimal(12), CoreBuyAction.BUY_INITIAL)
    position.apply_core_buy(Decimal(30), Decimal(11), CoreBuyAction.ADD)
    assert [fill.action for fill in position.core_buy_fills] == [
        CoreBuyAction.BUY_INITIAL, CoreBuyAction.BUY_INITIAL, CoreBuyAction.ADD
    ]
    assert position.core_quantity == position.broker_quantity == Decimal(130)
    assert position.core_cost == Decimal(1450) / Decimal(130)
    assert position.estimated_broker_cost == position.core_cost
    assert position.broker_display_cost == Decimal(0)
    assert position.same_day_buy_quantity == Decimal(130)
    assert position.core_same_day_buy_quantity == Decimal(130)
    assert position.old_sellable_quantity == Decimal(0)
    with pytest.raises(ValueError, match="昨日可卖核心仓"):
        position.apply_target_reduction(Decimal(10))
    assert position.broker_quantity == Decimal(130)
    assert position.core_quantity == Decimal(130)
    position.advance_trading_day(date(2026, 10, 9))
    assert position.old_sellable_quantity == Decimal(130)
    assert position.sellable_core_quantity == Decimal(130)
    position.apply_target_reduction(Decimal(30))
    assert position.broker_quantity == position.core_quantity == Decimal(100)


def test_core_buy_invalid_fill_is_atomic() -> None:
    position = state()
    before = (
        position.core_quantity, position.core_cost, position.broker_quantity,
        position.estimated_broker_cost, position.same_day_buy_quantity,
    )
    with pytest.raises(TypeError, match="BUY_INITIAL"):
        position.apply_core_buy(Decimal(10), Decimal(11), "ADD")
    with pytest.raises(ValueError, match="必须大于0"):
        position.apply_core_buy(Decimal(10), Decimal(0), CoreBuyAction.ADD)
    assert (
        position.core_quantity, position.core_cost, position.broker_quantity,
        position.estimated_broker_cost, position.same_day_buy_quantity,
    ) == before
    assert position.core_buy_fills == []


def test_partial_t_pnl_is_pending_until_full_cycle_close() -> None:
    position = state()
    cycle = position.start_t_cycle(TDirection.REVERSE, Decimal(100), Decimal("9.8"))
    assert position.close_t_cycle(cycle, Decimal(40), Decimal("10.1")) == Decimal("12.0")
    assert position.pending_t_pnl == Decimal("12.0")
    assert position.realized_t_pnl == Decimal(0)
    assert position.effective_cost == Decimal(10)
    assert position.close_t_cycle(cycle, Decimal(60), Decimal("10.2")) == Decimal("24.0")
    assert position.pending_t_pnl == Decimal(0)
    assert position.realized_t_pnl == Decimal("36.0")
    assert position.effective_cost == Decimal(10) - Decimal(36) / Decimal(700)


def test_converted_partial_t_pnl_remains_separate_across_day_roll() -> None:
    position = state()
    position.trading_day = date(2026, 10, 8)
    cycle = position.start_t_cycle(TDirection.REVERSE, Decimal(100), Decimal("9.8"))
    position.close_t_cycle(cycle, Decimal(40), Decimal(10))
    assert position.pending_t_pnl == Decimal("8.0")
    assert position.realized_t_pnl == Decimal(0)
    position.advance_trading_day(date(2026, 10, 9))
    assert cycle.status is TCycleStatus.CONVERTED
    assert position.pending_t_pnl == Decimal(0)
    assert position.converted_t_pnl == Decimal("8.0")
    assert position.realized_t_pnl == Decimal(0)
    assert position.core_quantity == Decimal(760)
    assert position.broker_quantity == Decimal(1060)
    assert position.core_same_day_buy_quantity == Decimal(0)
