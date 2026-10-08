from decimal import Decimal

import pytest

from app.position.engine import PositionState, TCycleStatus, TDirection


def test_reverse_t_close_rejects_missing_inventory_without_mutating_cycle() -> None:
    position = PositionState(
        core_quantity=Decimal("700"),
        core_cost=Decimal("10"),
        broker_quantity=Decimal("1000"),
        broker_cost=Decimal("10"),
    )
    cycle = position.start_t_cycle(TDirection.REVERSE, Decimal("100"), Decimal("9.8"))
    # Simulate a broker reconciliation/sell outside the T engine which has
    # consumed the inventory reserved for this reverse-T settlement.
    position.apply_broker_sell(Decimal("400"))
    assert position.broker_quantity == position.core_quantity

    with pytest.raises(ValueError, match="不得侵蚀核心仓"):
        position.close_t_cycle(cycle, Decimal("40"), Decimal("10.2"))

    assert cycle.status is TCycleStatus.OPEN
    assert cycle.matched_quantity == Decimal("0")
    assert cycle.matched_value == Decimal("0")
    assert position.realized_t_pnl == Decimal("0")
    assert position.completed_t_cycles_today == 0
    assert position.broker_quantity == Decimal("700")
