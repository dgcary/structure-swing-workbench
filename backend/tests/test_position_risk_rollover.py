from datetime import date
from decimal import Decimal

from app.position.engine import PositionState, TCycleStatus, TDirection


def test_reverse_t_is_included_in_live_account_exposure() -> None:
    position = PositionState(Decimal("700"), Decimal("10"), Decimal("1000"), Decimal("10"))
    assert position.total_market_exposure(Decimal("10")) == Decimal("10000")
    cycle = position.start_t_cycle(TDirection.REVERSE, Decimal("100"), Decimal("9.8"))
    assert position.total_market_exposure(Decimal("10")) == Decimal("11000")
    position.close_t_cycle(cycle, Decimal("40"), Decimal("10.1"))
    assert position.total_market_exposure(Decimal("10")) == Decimal("10600")
    assert position.reverse_t_temporary_exposure == Decimal("588.0")


def test_day_rollover_resets_complete_cycle_quota_and_reclassifies_open_t() -> None:
    position = PositionState(Decimal("700"), Decimal("10"), Decimal("1000"), Decimal("10"))
    position.advance_trading_day(date(2026, 10, 8))
    cycle = position.start_t_cycle(TDirection.POSITIVE, Decimal("100"), Decimal("11"))
    position.close_t_cycle(cycle, Decimal("100"), Decimal("10.5"))
    open_cycle = position.start_t_cycle(TDirection.POSITIVE, Decimal("50"), Decimal("11"))
    converted = position.advance_trading_day(date(2026, 10, 9))
    assert converted == (open_cycle,)
    assert open_cycle.status is TCycleStatus.CONVERTED
    assert position.completed_t_cycles_today == 0
    assert position.same_day_buy_quantity == Decimal("0")
    assert position.ordinary_t_reduction_quantity == Decimal("50")
    assert position.old_sellable_quantity == Decimal("950")
