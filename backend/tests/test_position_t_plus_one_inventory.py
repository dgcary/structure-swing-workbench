"""A-share T+1 inventory ledger: today's buys cannot be sold again today."""

from datetime import date
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


def test_positive_buyback_does_not_replenish_sellable_old_inventory() -> None:
    p = position()
    first = p.start_t_cycle(TDirection.POSITIVE, Decimal("100"), Decimal("11"))
    p.close_t_cycle(first, Decimal("100"), Decimal("10.5"))
    assert p.broker_quantity == Decimal("1000")
    assert p.same_day_buy_quantity == Decimal("100")
    assert p.old_sellable_quantity == Decimal("900")
    with pytest.raises(ValueError, match="不得侵蚀核心仓"):
        p.start_t_cycle(TDirection.POSITIVE, Decimal("201"), Decimal("11"))
    second = p.start_t_cycle(TDirection.POSITIVE, Decimal("200"), Decimal("11"))
    assert p.old_sellable_quantity == Decimal("700")
    p.close_t_cycle(second, Decimal("200"), Decimal("10.5"))
    assert p.old_sellable_quantity == Decimal("700")


def test_partial_reverse_t_consumes_old_shares_without_recycling_new_shares() -> None:
    p = position()
    first = p.start_t_cycle(TDirection.REVERSE, Decimal("100"), Decimal("9.8"))
    p.close_t_cycle(first, Decimal("40"), Decimal("10"))
    assert p.old_sellable_quantity == Decimal("960")
    assert p.same_day_buy_quantity == Decimal("100")
    with pytest.raises(ValueError, match="不得侵蚀核心仓"):
        p.start_t_cycle(TDirection.REVERSE, Decimal("201"), Decimal("9.8"))
    second = p.start_t_cycle(TDirection.REVERSE, Decimal("200"), Decimal("9.8"))
    p.close_t_cycle(first, Decimal("60"), Decimal("10"))
    p.close_t_cycle(second, Decimal("200"), Decimal("10"))
    assert p.old_sellable_quantity == Decimal("700")
    assert p.broker_quantity == Decimal("1000")


def test_raw_broker_sell_cannot_sell_same_day_buyback() -> None:
    p = position()
    first = p.start_t_cycle(TDirection.POSITIVE, Decimal("100"), Decimal("11"))
    p.close_t_cycle(first, Decimal("100"), Decimal("10"))
    with pytest.raises(ValueError, match="昨日可卖持仓"):
        p.apply_broker_sell(Decimal("901"))
    assert p.broker_quantity == Decimal("1000")


def test_next_trading_day_releases_prior_day_buyback_inventory() -> None:
    p = position()
    p.advance_trading_day(date(2026, 10, 7))
    first = p.start_t_cycle(TDirection.POSITIVE, Decimal("100"), Decimal("11"))
    p.close_t_cycle(first, Decimal("100"), Decimal("10"))
    assert p.old_sellable_quantity == Decimal("900")
    p.advance_trading_day(date(2026, 10, 8))
    assert p.old_sellable_quantity == Decimal("1000")
    assert p.same_day_buy_quantity == Decimal("0")
    second = p.start_t_cycle(TDirection.POSITIVE, Decimal("300"), Decimal("11"))
    assert second.remaining_quantity == Decimal("300")


def test_target_reduction_cannot_consume_reverse_t_reserved_old_inventory() -> None:
    p = position()
    reverse = p.start_t_cycle(TDirection.REVERSE, Decimal("100"), Decimal("9.8"))
    p.apply_broker_sell(Decimal("300"))
    before = (p.core_quantity, p.broker_quantity)
    with pytest.raises(ValueError, match="预留持仓"):
        p.apply_target_reduction(Decimal("1"))
    assert (p.core_quantity, p.broker_quantity) == before
    with pytest.raises(ValueError, match="不得侵蚀核心仓"):
        p.close_t_cycle(reverse, Decimal("10"), Decimal("10.2"))
