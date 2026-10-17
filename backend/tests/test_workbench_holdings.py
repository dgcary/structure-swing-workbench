"""M8 sourced holdings remain read-only and never claim a full account."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.account import AccountLedger, Fill, FillSide, correct_holding
from app.account.recording import apply_fill
from app.workbench.overview import build_overview

AT = datetime(2026, 10, 16, 9, 30, tzinfo=UTC)


def _fill(side: FillSide, quantity: str, fill_id: str = "f1") -> Fill:
    return Fill(
        fill_id=fill_id, symbol="600000", side=side,
        quantity=Decimal(quantity), price=Decimal(11),
        executed_at=AT + timedelta(minutes=1), source_id="broker-csv",
    )


def test_missing_holdings_are_unknown_not_empty_portfolio() -> None:
    overview = build_overview()
    assert overview["holdings"] is None
    assert overview["metrics"][3]["value"] is None


def test_snapshot_holding_keeps_provenance_and_no_invented_core_t() -> None:
    ledger = AccountLedger()
    correct_holding(
        ledger, symbol="600000", quantity=Decimal(100),
        cost=Decimal(10), at=AT, source_id="manual-1",
    )
    overview = build_overview(ledger)
    row = overview["holdings"][0]
    assert row["quantity"] == "100"
    assert row["broker_display_cost"] == "10"
    assert row["status"] == "snapshot"
    assert row["source"] == "manual/manual-1"
    assert row["core_quantity"] is None
    assert row["t_quantity"] is None
    assert overview["metrics"][3]["value"] is None


def test_later_fill_changes_quantity_but_invalidates_stale_cost() -> None:
    ledger = AccountLedger()
    correct_holding(
        ledger, symbol="600000", quantity=Decimal(100),
        cost=Decimal(10), at=AT, source_id="manual-1",
    )
    apply_fill(ledger, _fill(FillSide.BUY, "20"))
    row = build_overview(ledger)["holdings"][0]
    assert row["quantity"] == "120"
    assert row["broker_display_cost"] is None
    assert row["status"] == "partial"
    assert row["applied_fill_ids"] == ["f1"]


def test_unanchored_fills_never_become_a_position() -> None:
    ledger = AccountLedger()
    apply_fill(ledger, _fill(FillSide.BUY, "20"))
    row = build_overview(ledger)["holdings"][0]
    assert row["quantity"] is None
    assert row["unanchored_fill_delta"] == "20"
    assert row["status"] == "unanchored"
    assert row["source"] == "成交记录/broker-csv"
    assert row["applied_fill_ids"] == ["f1"]
    assert row["as_of"] == (AT + timedelta(minutes=1)).isoformat()


def test_inconsistent_sell_is_marked_conflict_not_negative_holding() -> None:
    ledger = AccountLedger()
    correct_holding(
        ledger, symbol="600000", quantity=Decimal(10),
        cost=Decimal(10), at=AT, source_id="manual-1",
    )
    apply_fill(ledger, _fill(FillSide.SELL, "20"))
    row = build_overview(ledger)["holdings"][0]
    assert row["status"] == "conflict"
    assert row["quantity"] is None
    assert row["broker_display_cost"] is None
