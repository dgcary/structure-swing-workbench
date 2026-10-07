from decimal import Decimal

import pytest

from app.position.engine import PositionState, TDirection


def test_reverse_t_partial_fill_preserves_old_inventory_reservation() -> None:
    position = PositionState(
        core_quantity=Decimal("700"),
        core_cost=Decimal("10"),
        broker_quantity=Decimal("1000"),
        broker_cost=Decimal("10"),
    )
    first = position.start_t_cycle(TDirection.REVERSE, Decimal("100"), Decimal("9.8"))
    position.close_t_cycle(first, Decimal("40"), Decimal("10.1"))
    second = position.start_t_cycle(TDirection.REVERSE, Decimal("200"), Decimal("9.9"))
    assert first.remaining_quantity == Decimal("60")
    assert second.remaining_quantity == Decimal("200")
    with pytest.raises(ValueError, match="不得侵蚀核心仓"):
        position.start_t_cycle(TDirection.REVERSE, Decimal("41"), Decimal("9.9"))
