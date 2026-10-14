"""Read-only holdings derived from a dated snapshot and subsequent fills."""

from decimal import Decimal

from app.account.ledger import AccountLedger
from app.account.models import FillSide, ImportConflictError, PositionView


def position_view(ledger: AccountLedger, symbol: str) -> PositionView:
    baseline = ledger.facts.get(f"position:{symbol}:quantity")
    cost = ledger.facts.get(f"position:{symbol}:cost")
    later = [
        item for item in ledger.fills.values()
        if item.symbol == symbol and (
            baseline is None or item.executed_at > baseline.observed_at
        )
    ]
    delta = sum(
        (f.quantity if f.side is FillSide.BUY else -f.quantity for f in later),
        Decimal(0),
    )
    quantity = baseline.value + delta if baseline else None
    if quantity is not None and quantity < 0:
        raise ImportConflictError("成交数量与持仓快照不一致")
    current_cost = (
        cost.value if cost and baseline and cost.observed_at == baseline.observed_at
        and cost.source_id == baseline.source_id and not later else None
    )
    return PositionView(
        symbol, quantity, delta if baseline is None else Decimal(0),
        current_cost, baseline.observed_at if baseline else None,
        tuple(f.fill_id for f in later),
    )
