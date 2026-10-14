"""Confirmed executions cannot be silently changed by later CSV files."""

import pytest

from app.account import AccountLedger, ImportConflictError, import_csv, position_view

T = "2026-10-13T10:00:00+08:00"


def test_same_execution_id_rejects_conflicting_content() -> None:
    book = AccountLedger()
    header = "fill_id,symbol,side,quantity,price,executed_at\n"
    first = header + f"E1,TEST,BUY,10,10,{T}\n"
    assert import_csv(book, "fills", first, batch_id="first").imported == 1
    assert import_csv(book, "fills", first, batch_id="repeat").duplicates == 1
    with pytest.raises(ImportConflictError):
        import_csv(book, "fills", header + f"E1,TEST,BUY,11,10,{T}\n", batch_id="changed")
    assert len(book.fills) == 1
    assert "changed" not in book.batches
    assert position_view(book, "TEST").quantity is None
