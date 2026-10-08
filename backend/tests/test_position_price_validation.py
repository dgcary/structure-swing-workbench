from decimal import Decimal

import pytest

from app.position.engine import PositionState, TDirection


def test_cycle_open_rejects_non_positive_price() -> None:
    position = PositionState(Decimal(700), Decimal(10), Decimal(1000), Decimal(10))
    with pytest.raises(ValueError):
        position.start_t_cycle(TDirection.REVERSE, Decimal(10), Decimal(0))
