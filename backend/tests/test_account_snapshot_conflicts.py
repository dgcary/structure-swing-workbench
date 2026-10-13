"""Conflicting snapshots remain visible and never silently overwrite."""

from decimal import Decimal

from app.account import AccountLedger, import_csv

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
