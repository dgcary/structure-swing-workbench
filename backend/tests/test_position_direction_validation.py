from decimal import Decimal

import pytest

from app.position.engine import PositionState, TDirection


@pytest.mark.parametrize("direction", ["positive", "reverse", None, "unknown"])
def test_invalid_t_direction_cannot_mutate_broker_inventory(direction: object) -> None:
    position = PositionState(
        core_quantity=Decimal(700),
        core_cost=Decimal(10),
        broker_quantity=Decimal(1000),
        broker_cost=Decimal(10),
    )
    with pytest.raises(TypeError, match="方向必须为正T或反T"):
        position.start_t_cycle(direction, Decimal(100), Decimal(10))
    assert position.broker_quantity == Decimal(1000)
    assert position.broker_cost == Decimal(10)
    assert position.t_cycles == []


def test_enum_t_direction_is_accepted() -> None:
    position = PositionState(
        core_quantity=Decimal(700),
        core_cost=Decimal(10),
        broker_quantity=Decimal(1000),
        broker_cost=Decimal(10),
    )
    cycle = position.start_t_cycle(TDirection.POSITIVE, Decimal(10), Decimal(11))
    assert cycle.direction is TDirection.POSITIVE
    assert position.broker_quantity == Decimal(990)
