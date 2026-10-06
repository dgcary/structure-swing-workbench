from decimal import Decimal

import pytest

from app.position.engine import PositionState, TCycle, TDirection


def test_foreign_cycle_cannot_be_closed_against_position_state() -> None:
    position = PositionState(
        core_quantity=Decimal("700"),
        core_cost=Decimal("10"),
        broker_quantity=Decimal("1000"),
        broker_cost=Decimal("10"),
    )
    foreign_cycle = TCycle(
        direction=TDirection.REVERSE,
        open_quantity=Decimal("100"),
        open_price=Decimal("9.8"),
    )

    with pytest.raises(ValueError):
        position.close_t_cycle(foreign_cycle, Decimal("100"), Decimal("10.2"))
