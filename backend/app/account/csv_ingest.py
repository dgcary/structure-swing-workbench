"""Atomic CSV batch import with provenance and idempotency."""

from copy import deepcopy
from decimal import Decimal
from hashlib import sha256

from app.account.csv_rows import apply_row
from app.account.imports import parse_number, parse_rows, parse_time
from app.account.ledger import AccountLedger
from app.account.models import FillSide, ImportConflictError, ImportResult, SourceKind
from app.account.position_view import position_view

SCHEMAS = {
    "fills": ("fill_id", "symbol", "side", "quantity", "price", "executed_at"),
    "holdings": ("symbol", "quantity", "cost", "as_of"),
    "account": ("equity", "available_cash", "as_of"),
}


def _check_snapshot_against_fills(ledger: AccountLedger, row: dict[str, str]) -> None:
    """Do not let a newer snapshot silently erase confirmed intervening fills."""
    symbol = row["symbol"]
    previous = ledger.facts.get(f"position:{symbol}:quantity")
    if previous is None or previous.source is not SourceKind.SNAPSHOT:
        return
    observed_at = parse_time(row["as_of"])
    if observed_at <= previous.observed_at:
        return
    intervening = [
        fill for fill in ledger.fills.values()
        if fill.symbol == symbol
        and previous.observed_at < fill.executed_at <= observed_at
    ]
    if not intervening:
        return
    delta = sum(
        (
            fill.quantity if fill.side is FillSide.BUY else -fill.quantity
            for fill in intervening
        ),
        Decimal(0),
    )
    expected = previous.value + delta
    incoming = parse_number(row["quantity"], "持仓数量")
    if incoming != expected:
        raise ImportConflictError(
            f"持仓快照 {symbol} 与期间已确认成交冲突："
            f"预计数量 {expected}，导入数量 {incoming}；"
            "请核对缺失成交或快照口径"
        )


def import_csv(ledger: AccountLedger, kind: str, data: str, *, batch_id: str) -> ImportResult:
    if not batch_id.strip():
        raise ValueError("batch_id 不能为空")
    if kind not in SCHEMAS:
        raise ValueError("未知 CSV 类型")
    digest = sha256((kind + "\0" + data).encode("utf-8")).hexdigest()
    if batch_id in ledger.batches:
        if ledger.batches[batch_id] == digest:
            return ImportResult(0, 0, 0, batch_duplicate=True)
        raise ImportConflictError("同一 batch_id 对应不同内容")
    rows = parse_rows(data, SCHEMAS[kind])
    if kind == "account" and len(rows) != 1:
        raise ValueError("账户快照每批只能有一行")
    staged = deepcopy(ledger)
    imported = duplicates = 0
    before = len(staged.conflicts)
    symbols: set[str] = set()
    for row in rows:
        if kind == "holdings":
            _check_snapshot_against_fills(staged, row)
        count, duplicate, symbol = apply_row(staged, kind, row, batch_id)
        if symbol:
            if kind == "holdings" and symbol in symbols:
                raise ValueError("同批持仓快照重复证券代码")
            symbols.add(symbol)
        imported += count
        duplicates += duplicate
    for symbol in symbols:
        position_view(staged, symbol)
    staged.batches[batch_id] = digest
    ledger.facts = staged.facts
    ledger.fills = staged.fills
    ledger.batches = staged.batches
    ledger.audit = staged.audit
    ledger.conflicts = staged.conflicts
    return ImportResult(imported, duplicates, len(ledger.conflicts) - before)
