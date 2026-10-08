"""Regression coverage for per-stock completed T-cycle accounting."""

from decimal import Decimal

import pytest

from app.position.engine import PositionState, TCycleStatus, TDirection


def test_two_closed_cycles_cannot_be_evaded_with_preopened_positive_t() -> None:
    position = PositionState(
        core_quantity=Decimal("700"),
        core_cost=Decimal("10"),
        broker_quantity=Decimal("1000"),
        broker_cost=Decimal("10"),
    )
    cycles = [
        position.start_t_cycle(TDirection.POSITIVE, Decimal("50"), Decimal("11"))
        for _ in range(3)
    ]
    for cycle in cycles[:2]:
        position.close_t_cycle(cycle, Decimal("50"), Decimal("10.5"))
    before = (position.realized_t_pnl, position.broker_quantity)
    with pytest.raises(ValueError, match="最多2个完整T闭环"):
        position.close_t_cycle(cycles[2], Decimal("10"), Decimal("10.5"))
    assert cycles[2].status is TCycleStatus.OPEN
    assert cycles[2].matched_quantity == Decimal("0")
    assert (position.realized_t_pnl, position.broker_quantity) == before
