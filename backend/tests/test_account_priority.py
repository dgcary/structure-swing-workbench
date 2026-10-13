"""M5 source precedence and idempotency regression tests."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.account import AccountLedger, ImportConflictError, correct_account, import_csv

T = "2026-10-13T10:00:00+08:00"


def test_snapshot_overrides_manual_but_not_reverse() -> None:
    book = AccountLedger()
    correct_account(
        book, equity=Decimal("9000"), cash=Decimal("4000"),
        at=datetime(2026, 10, 12, tzinfo=timezone.utc), source_id="manual",
    )
    data = f"equity,available_cash,as_of\n10000,5000,{T}\n"
    assert import_csv(book, "account", data, batch_id="snapshot").imported == 2
    assert book.facts["account.equity"].value == Decimal("10000")
    correct_account(
        book, equity=Decimal("20000"), cash=Decimal("8000"),
        at=datetime(2026, 10, 14, tzinfo=timezone.utc), source_id="later",
    )
    assert book.facts["account.equity"].value == Decimal("10000")
    assert len(book.conflicts) == 2
    assert any(e.action == "supersede" for e in book.audit)


def test_batch_idempotency_and_conflicting_payload() -> None:
    book = AccountLedger()
    data = f"equity,available_cash,as_of\n100,40,{T}\n"
    assert import_csv(book, "account", data, batch_id="a").imported == 2
    assert import_csv(book, "account", data, batch_id="a").batch_duplicate
    with pytest.raises(ImportConflictError):
        import_csv(book, "account", data.replace("100,40", "110,40"), batch_id="a")
