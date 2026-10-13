"""Atomic CSV batch import with provenance and idempotency."""

from copy import deepcopy
from hashlib import sha256

from app.account.csv_rows import apply_row
from app.account.imports import parse_rows
from app.account.ledger import AccountLedger
from app.account.models import ImportConflictError, ImportResult
from app.account.position_view import position_view

SCHEMAS = {
    "fills": ("fill_id", "symbol", "side", "quantity", "price", "executed_at"),
    "holdings": ("symbol", "quantity", "cost", "as_of"),
    "account": ("equity", "available_cash", "as_of"),
}


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
