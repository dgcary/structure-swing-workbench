from decimal import Decimal

import pytest

from app.position.engine import PositionState, TDirection


def position() -> PositionState:
    return PositionState(
        core_quantity=Decimal("700"),
        core_cost=Decimal("10"),
        broker_quantity=Decimal("1000"),
        broker_cost=Decimal("10"),
    )


@pytest.mark.parametrize("quantity", [Decimal("0"), Decimal("-1")])
def test_t_cycle_rejects_non_positive_quantity(quantity: Decimal) -> None:
    with pytest.raises(ValueError, match="数量必须大于0"):
        position().start_t_cycle(TDirection.REVERSE, quantity, Decimal("10"))


def test_partial_close_cannot_exceed_remaining_quantity() -> None:
    current = position()
    cycle = current.start_t_cycle(TDirection.REVERSE, Decimal("100"), Decimal("9.8"))
    current.close_t_cycle(cycle, Decimal("40"), Decimal("10"))
    with pytest.raises(ValueError, match="不超过未匹配数量"):
        current.close_t_cycle(cycle, Decimal("61"), Decimal("10"))
