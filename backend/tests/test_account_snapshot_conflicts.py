"""Conflicting snapshots remain visible and never silently overwrite."""

from datetime import datetime
from decimal import Decimal

import pytest

from app.account import (
    AccountLedger,
    ImportConflictError,
    correct_holding,
    import_csv,
    position_view,
)

T = "2026-10-13T10:00:00+08:00"
LATER = "2026-10-13T11:00:00+08:00"


def test_same_time_conflict_and_newer_snapshot_audited() -> None:
    book = AccountLedger()
    header = "symbol,quantity,cost,as_of\n"
    import_csv(book, "holdings", header + f"TEST,20,10,{T}\n", batch_id="a")
    result = import_csv(
        book, "holdings", header + f"TEST,30,11,{T}\n", batch_id="b"
    )
    assert result.conflicts == 2
    assert book.facts["position:TEST:quantity"].value == Decimal(20)
    import_csv(book, "holdings", header + f"TEST,40,12,{LATER}\n", batch_id="c")
    assert book.facts["position:TEST:quantity"].value == Decimal(40)
    assert any(event.action == "supersede" for event in book.audit)


def _manual_with_fill() -> AccountLedger:
    book = AccountLedger()
    correct_holding(
        book, symbol="TEST", quantity=Decimal(100), cost=Decimal(10),
        at=datetime.fromisoformat(T), source_id="manual-baseline",
    )
    import_csv(
        book, "fills",
        "fill_id,symbol,side,quantity,price,executed_at\n"
        "E1,TEST,BUY,10,11,2026-10-13T10:30:00+08:00\n",
        batch_id="confirmed",
    )
    return book


def test_manual_baseline_cannot_hide_confirmed_fill() -> None:
    book = _manual_with_fill()
    audit_before = list(book.audit)
    with pytest.raises(ImportConflictError, match="已确认成交冲突.*110.*100"):
        import_csv(
            book, "holdings",
            "symbol,quantity,cost,as_of\n"
            "TEST,100,10,2026-10-13T11:00:00+08:00\n",
            batch_id="conflicting-snapshot",
        )
    assert "conflicting-snapshot" not in book.batches
    assert book.audit == audit_before
    assert position_view(book, "TEST").quantity == Decimal(110)
    assert position_view(book, "TEST").applied_fill_ids == ("E1",)


def test_manual_baseline_accepts_consistent_snapshot() -> None:
    book = _manual_with_fill()
    result = import_csv(
        book, "holdings",
        "symbol,quantity,cost,as_of\n"
        "TEST,110,10.5,2026-10-13T11:00:00+08:00\n",
        batch_id="reconciled-snapshot",
    )
    assert result.imported == 2
    view = position_view(book, "TEST")
    assert view.quantity == Decimal(110)
    assert view.applied_fill_ids == ()
    assert view.broker_display_cost == Decimal("10.5")
