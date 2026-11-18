"""T-cycle grouping and daily-limit view over persisted T actions and fills.

Pure module: it summarizes ordered fill lists and never touches the database.
配对规则与持仓引擎一致：FIFO 买卖配对，已配对部分毛盈亏 =（卖价 − 买价）× 数量。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.enums import ActionType, OrderSide

T_CYCLE_ACTION_TYPES = frozenset(
    {
        ActionType.POSITIVE_T_SELL,
        ActionType.POSITIVE_T_BUYBACK,
        ActionType.REVERSE_T_BUY,
        ActionType.REVERSE_T_SELL,
    }
)

MAX_COMPLETED_CYCLES_PER_DAY = 2

CYCLE_COMPLETED = "completed"
CYCLE_OPEN = "open"


@dataclass(frozen=True, slots=True)
class CycleFill:
    side: OrderSide
    quantity: Decimal
    price: Decimal


@dataclass(frozen=True, slots=True)
class CycleSummary:
    matched_quantity: Decimal
    matched_gross_pnl: Decimal
    remaining_quantity: Decimal
    open_side: OrderSide | None
    completed: bool


def summarize_cycle(fills: list[CycleFill]) -> CycleSummary:
    """FIFO 买卖配对；未配对部分为剩余仓位。"""

    buys: list[list[Decimal]] = []
    sells: list[list[Decimal]] = []
    matched_quantity = Decimal(0)
    pnl = Decimal(0)
    for fill in fills:
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
            matched_quantity += take
            quantity -= take
            opposite[0][0] -= take
            if opposite[0][0] <= 0:
                opposite.pop(0)
        if quantity > 0:
            same.append([quantity, fill.price])
    remaining = sum((item[0] for item in buys), Decimal(0)) + sum(
        (item[0] for item in sells), Decimal(0)
    )
    open_side = OrderSide.BUY if buys else (OrderSide.SELL if sells else None)
    return CycleSummary(matched_quantity, pnl, remaining, open_side, remaining == 0)


def exceeds_daily_limit(completed_days: dict[date, int]) -> bool:
    """每只股票每天最多完成 2 个完整 T 循环（trading-rules.md §10）。"""

    return any(count > MAX_COMPLETED_CYCLES_PER_DAY for count in completed_days.values())
