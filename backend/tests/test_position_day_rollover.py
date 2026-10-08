"""Trading-day rollover invariants for T-cycle accounting."""

from datetime import date
from decimal import Decimal

import pytest

from app.position.engine import PositionState, TCycleStatus, TDirection


def position() -> PositionState:
    return PositionState(
        core_quantity=Decimal("700"),
        core_cost=Decimal("10"),
        broker_quantity=Decimal("1000"),
        broker_cost=Decimal("10"),
    )


def test_new_day_converts_unclosed_t_once_and_resets_completed_quota() -> None:
    p = position()
    assert p.advance_trading_day(date(2026, 10, 7)) == ()
    complete = p.start_t_cycle(TDirection.POSITIVE, Decimal("10"), Decimal("11"))
    p.close_t_cycle(complete, Decimal("10"), Decimal("10"))
    incomplete = p.start_t_cycle(TDirection.REVERSE, Decimal("20"), Decimal("9"))
    assert p.completed_t_cycles_today == 1
    assert p.advance_trading_day(date(2026, 10, 8)) == (incomplete,)
    assert incomplete.status is TCycleStatus.CONVERTED
    assert p.ordinary_t_addition_quantity == Decimal("20")
    assert p.core_quantity == Decimal("720")
    assert p.completed_t_cycles_today == 0
    assert p.advance_trading_day(date(2026, 10, 8)) == ()
    assert p.ordinary_t_addition_quantity == Decimal("20")


def test_same_day_cannot_reset_exhausted_quota() -> None:
    p = position()
    p.advance_trading_day(date(2026, 10, 7))
    for _ in range(2):
        c = p.start_t_cycle(TDirection.POSITIVE, Decimal("10"), Decimal("11"))
        p.close_t_cycle(c, Decimal("10"), Decimal("10"))
    p.advance_trading_day(date(2026, 10, 7))
    with pytest.raises(ValueError, match="最多2个完整T闭环"):
        p.start_t_cycle(TDirection.POSITIVE, Decimal("10"), Decimal("11"))


def test_backdated_or_unanchored_rollover_is_rejected() -> None:
    p = position()
    p.advance_trading_day(date(2026, 10, 8))
    with pytest.raises(ValueError, match="不得倒退"):
        p.advance_trading_day(date(2026, 10, 7))
    assert p.trading_day == date(2026, 10, 8)
    with pytest.raises(TypeError, match="date"):
        p.advance_trading_day("2026-10-09")

    legacy = position()
    legacy.start_t_cycle(TDirection.POSITIVE, Decimal("10"), Decimal("11"))
    with pytest.raises(ValueError, match="初始交易日"):
        legacy.advance_trading_day(date(2026, 10, 8))
