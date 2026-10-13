"""CSV snapshot chronology must preserve subsequent confirmed executions."""

from decimal import Decimal

from app.account import AccountLedger, import_csv, position_view


def test_snapshot_preceding_confirmed_fill_keeps_fill_delta() -> None:
    ledger = AccountLedger()
    import_csv(
        ledger, "holdings",
        "symbol,quantity,cost,as_of\nTEST,100,10,2026-10-13T10:00:00+08:00\n",
        batch_id="first",
    )
    import_csv(
        ledger, "fills",
        "fill_id,symbol,side,quantity,price,executed_at\n"
        "E1,TEST,BUY,10,11,2026-10-13T11:00:00+08:00\n",
        batch_id="execution",
    )
    import_csv(
        ledger, "holdings",
        "symbol,quantity,cost,as_of\nTEST,100,10,2026-10-13T10:30:00+08:00\n",
        batch_id="second",
    )
    view = position_view(ledger, "TEST")
    assert view.quantity == Decimal(110)
    assert view.applied_fill_ids == ("E1",)
