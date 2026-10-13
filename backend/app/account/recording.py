"""Immutable execution IDs and auditable manual account corrections."""

from datetime import datetime
from decimal import Decimal

from app.account.ledger import AccountLedger
from app.account.models import AuditEvent, Conflict, Fact, Fill, ImportConflictError, SourceKind


def apply_fill(ledger: AccountLedger, item: Fill) -> bool:
    if not item.fill_id or not item.symbol or not item.source_id:
        raise ValueError("成交缺少编号、代码或来源")
    if item.executed_at.tzinfo is None or item.executed_at.utcoffset() is None:
        raise ValueError("成交时间缺少时区")
    if item.quantity <= 0 or not item.quantity.is_finite():
        raise ValueError("成交数量无效")
    if item.price <= 0 or not item.price.is_finite():
        raise ValueError("成交价格无效")
    old = ledger.fills.get(item.fill_id)
    if old is not None:
        a = (old.symbol, old.side, old.quantity, old.price, old.executed_at)
        b = (item.symbol, item.side, item.quantity, item.price, item.executed_at)
        if a == b:
            return False
        ledger.conflicts.append(Conflict(item.fill_id, str(old), str(item), "成交编号冲突"))
        raise ImportConflictError(f"成交编号冲突：{item.fill_id}")
    ledger.fills[item.fill_id] = item
    ledger.audit.append(AuditEvent("fill", item.fill_id, item.source_id, "确认成交"))
    return True


def correct_account(
    ledger: AccountLedger, *, equity: Decimal, cash: Decimal, at: datetime, source_id: str
) -> None:
    ledger.record_fact(Fact("account.equity", equity, SourceKind.MANUAL, source_id, at))
    ledger.record_fact(Fact("account.available_cash", cash, SourceKind.MANUAL, source_id, at))


def correct_holding(
    ledger: AccountLedger, *, symbol: str, quantity: Decimal, cost: Decimal,
    at: datetime, source_id: str
) -> None:
    if not symbol.strip():
        raise ValueError("证券代码不能为空")
    for suffix, value in (("quantity", quantity), ("cost", cost)):
        ledger.record_fact(Fact(f"position:{symbol}:{suffix}", value, SourceKind.MANUAL, source_id, at))
