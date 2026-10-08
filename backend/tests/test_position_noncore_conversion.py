from decimal import Decimal

from app.position.engine import PositionState, TDirection


def test_unclosed_positive_t_preserves_core_quantity() -> None:
    position = PositionState(
        core_quantity=Decimal(700),
        core_cost=Decimal(10),
        broker_quantity=Decimal(1000),
        broker_cost=Decimal(10),
    )
    position.start_t_cycle(TDirection.POSITIVE, Decimal(100), Decimal(11))
    position.convert_open_cycles_at_day_end()
    assert position.core_quantity == Decimal(700)
    assert position.broker_quantity == Decimal(900)
