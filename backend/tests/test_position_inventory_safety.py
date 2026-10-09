from decimal import Decimal

import pytest

from app.position.engine import BrokerInventoryConflict, PositionState, TDirection


def test_core_and_reserved_inventory_are_protected() -> None:
    state = PositionState(Decimal(700), Decimal(10), Decimal(1000), Decimal(10))
    with pytest.raises(BrokerInventoryConflict):
        state.apply_broker_sell(Decimal(500))
    assert state.broker_quantity == Decimal(1000)
    cycle = state.start_t_cycle(TDirection.REVERSE, Decimal(100), Decimal(10))
    with pytest.raises(BrokerInventoryConflict):
        state.apply_broker_sell(Decimal(201))
    assert state.broker_quantity == Decimal(1100)
    assert cycle.matched_quantity == Decimal(0)


def test_reverse_t_stop_is_downside_only() -> None:
    state = PositionState(Decimal(700), Decimal(10), Decimal(1000), Decimal(10))
    assert state.t_stop_risk(Decimal(100), Decimal(10), Decimal(9)) == Decimal(100)
    with pytest.raises(ValueError):
        state.t_stop_risk(Decimal(100), Decimal(10), Decimal(11))
