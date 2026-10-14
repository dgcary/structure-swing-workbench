"""Reject newer holdings snapshots inconsistent with confirmed executions."""

from decimal import Decimal

import pytest

from app.account import (
    AccountLedger,
    ImportConflictError,
    import_csv,
    position_view,
)

HEADER = "symbol,quantity,cost,as_of\n"
FILL_HEADER = "fill_id,symbol,side,quantity,price,executed_at\n"


def _ledger_with_fill() -> AccountLedger:
    ledger = AccountLedger()
    import_csv(
        ledger, "holdings",
        HEADER + "TEST,100,10,2026-10-13T10:00:00+08:00\n",
        batch_id="baseline",
    )
    import_csv(
        ledger, "fills",
        FILL_HEADER + "E1,TEST,BUY,10,11,2026-10-13T11:00:00+08:00\n",
        batch_id="confirmed",
    )
    return ledger


def test_newer_snapshot_cannot_discard_known_fill() -> None:
    ledger = _ledger_with_fill()
    with pytest.raises(ImportConflictError, match="已确认成交冲突"):
        import_csv(
            ledger, "holdings",
            HEADER + "TEST,100,10,2026-10-13T12:00:00+08:00\n",
            batch_id="contradiction",
        )
    assert "contradiction" not in ledger.batches
    assert ledger.facts["position:TEST:quantity"].value == Decimal(100)
    assert position_view(ledger, "TEST").quantity == Decimal(110)


def test_consistent_newer_snapshot_absorbs_preceding_fill() -> None:
    ledger = _ledger_with_fill()
    result = import_csv(
        ledger, "holdings",
        HEADER + "TEST,110,10.5,2026-10-13T12:00:00+08:00\n",
        batch_id="consistent",
    )
    assert result.imported == 2
    view = position_view(ledger, "TEST")
    assert view.quantity == Decimal(110)
    assert view.applied_fill_ids == ()
    assert view.broker_display_cost == Decimal("10.5")
