"""Day-end conversion must not hide a broker inventory discrepancy."""

from datetime import date
from decimal import Decimal

import pytest

from app.position.engine import PositionState, TCycleStatus, TDirection


def test_conversion_rejects_insufficient_broker_inventory_without_partial_changes() -> None:
    state = PositionState(Decimal(700), Decimal(10), Decimal(1000), Decimal(10))
    state.advance_trading_day(date(2026, 10, 8))
    positive = state.start_t_cycle(TDirection.POSITIVE, Decimal(100), Decimal(11))
    reverse = state.start_t_cycle(TDirection.REVERSE, Decimal(100), Decimal(9))
    # Simulate an out-of-band broker discrepancy that bypassed the protected API.
    state.broker_quantity -= Decimal(300)

    before = (
        state.core_quantity,
        state.core_cost,
        state.ordinary_t_addition_quantity,
        state.ordinary_t_reduction_quantity,
        state.completed_t_cycles_today,
        state.trading_day,
    )
    with pytest.raises(ValueError, match="超过券商持仓"):
        state.advance_trading_day(date(2026, 10, 9))

    assert positive.status is TCycleStatus.OPEN
    assert reverse.status is TCycleStatus.OPEN
    assert (
        state.core_quantity,
        state.core_cost,
        state.ordinary_t_addition_quantity,
        state.ordinary_t_reduction_quantity,
        state.completed_t_cycles_today,
        state.trading_day,
    ) == before


def test_valid_mixed_day_end_conversion_still_succeeds() -> None:
    state = PositionState(Decimal(700), Decimal(10), Decimal(1000), Decimal(10))
    positive = state.start_t_cycle(TDirection.POSITIVE, Decimal(100), Decimal(11))
    reverse = state.start_t_cycle(TDirection.REVERSE, Decimal(100), Decimal(9))

    assert state.convert_open_cycles_at_day_end() == (positive, reverse)
    assert state.core_quantity == Decimal(800)
    assert state.broker_quantity == Decimal(1000)
    assert state.ordinary_t_addition_quantity == Decimal(100)
    assert state.ordinary_t_reduction_quantity == Decimal(100)
