"""Plan review summary: planned vs actual, pure computations only."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.domain.enums import OrderSide

LONG_HOLDING_DAYS = 10


@dataclass(frozen=True, slots=True)
class ReviewFill:
    side: OrderSide
    quantity: Decimal
    price: Decimal
    executed_at: datetime


@dataclass(frozen=True, slots=True)
class PlanReview:
    total_buy_quantity: Decimal
    total_sell_quantity: Decimal
    avg_buy_price: Decimal | None
    avg_sell_price: Decimal | None
    remaining_quantity: Decimal
    realized_gross_pnl: Decimal
    first_fill_at: datetime | None
    last_fill_at: datetime | None
    holding_days: int | None
    long_holding_note: str | None
    entry_deviation_pct: Decimal | None


def review_fills(fills: list[ReviewFill], planned_entry_low: Decimal | None) -> PlanReview:
    """汇总计划的实际成交；毛盈亏按 FIFO 买卖配对（卖价 − 买价）× 数量。"""

    buys: list[list[Decimal]] = []
    sells: list[list[Decimal]] = []
    total_buy = Decimal(0)
    total_sell = Decimal(0)
    buy_amount = Decimal(0)
    sell_amount = Decimal(0)
    pnl = Decimal(0)
    ordered = sorted(fills, key=lambda item: item.executed_at)
    for fill in ordered:
        if fill.side is OrderSide.BUY:
            total_buy += fill.quantity
            buy_amount += fill.price * fill.quantity
        else:
            total_sell += fill.quantity
            sell_amount += fill.price * fill.quantity
        quantity = fill.quantity
        opposite, same = (sells, buys) if fill.side is OrderSide.BUY else (buys, sells)
        while quantity > 0 and opposite:
            take = min(quantity, opposite[0][0])
            buy_price, sell_price = (
                (opposite[0][1], fill.price)
                if fill.side is OrderSide.SELL
                else (fill.price, opposite[0][1])
            )
            pnl += (sell_price - buy_price) * take
            quantity -= take
            opposite[0][0] -= take
            if opposite[0][0] <= 0:
                opposite.pop(0)
        if quantity > 0:
            same.append([quantity, fill.price])
    remaining = sum((item[0] for item in buys), Decimal(0)) + sum(
        (item[0] for item in sells), Decimal(0)
    )

    first_fill = ordered[0].executed_at if ordered else None
    last_fill = ordered[-1].executed_at if ordered else None
    holding_days: int | None = None
    note: str | None = None
    if first_fill is not None and last_fill is not None:
        holding_days = (last_fill.date() - first_fill.date()).days
        if holding_days > LONG_HOLDING_DAYS:
            note = f"持有超过 {LONG_HOLDING_DAYS} 日，不构成违规，仅记录用于复盘"

    entry_deviation: Decimal | None = None
    first_buy = next((fill for fill in ordered if fill.side is OrderSide.BUY), None)
    if (
        planned_entry_low is not None
        and planned_entry_low > 0
        and first_buy is not None
    ):
        entry_deviation = (
            (first_buy.price - planned_entry_low) / planned_entry_low * Decimal(100)
        ).quantize(Decimal("0.0001"))

    return PlanReview(
        total_buy_quantity=total_buy,
        total_sell_quantity=total_sell,
        avg_buy_price=(buy_amount / total_buy).quantize(Decimal("0.0001")) if total_buy > 0 else None,
        avg_sell_price=(sell_amount / total_sell).quantize(Decimal("0.0001"))
        if total_sell > 0
        else None,
        remaining_quantity=remaining,
        realized_gross_pnl=pnl,
        first_fill_at=first_fill,
        last_fill_at=last_fill,
        holding_days=holding_days,
        long_holding_note=note,
        entry_deviation_pct=entry_deviation,
    )
