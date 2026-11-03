"""A manual journal is a versioned self-report, never a formal broker fact."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import AccountSnapshot, ExecutionFill, ManualJournalRevision
from app.workbench.manual_journal import (
    ManualJournalWrite,
    ManualOperationApply,
    append_manual_record,
    apply_manual_operation,
    read_manual_records,
)


def _payload(expected_revision=0, **changes):
    now = datetime.now(UTC).replace(microsecond=0)
    values = {
        "expected_revision": expected_revision,
        "observed_at": now,
        "available_cash": "1234.56",
        "total_equity": None,
        "lots": [{
            "symbol": "600000.SH", "quantity": "100", "paid_amount": "980",
            "bought_at": now - timedelta(days=1),
        }],
        "operation": None,
        "note": "",
    }
    values.update(changes)
    return ManualJournalWrite(**values)


def test_append_and_read_manual_revisions_without_formal_promotion(session: Session):
    first = append_manual_record(session, _payload())
    session.commit()
    assert first["revision"] == 1
    assert first["source"] == "user_manual"
    assert first["broker_reconciled"] is False
    assert first["trade_execution_enabled"] is False
    assert first["lots"][0]["paid_amount"] == "980"

    second = append_manual_record(session, _payload(
        expected_revision=1, available_cash="250.56",
        operation={"side": "BUY", "symbol": "600000.SH", "quantity": "100",
                   "price": "9.80", "executed_at": datetime.now(UTC) - timedelta(minutes=2)},
    ))
    session.commit()
    journal = read_manual_records(session)
    assert second["revision"] == 2
    assert journal["latest"]["id"] == second["id"]
    assert [row["revision"] for row in journal["history"]] == [2, 1]
    assert session.scalar(select(func.count()).select_from(ManualJournalRevision)) == 2
    assert session.scalar(select(func.count()).select_from(AccountSnapshot)) == 0
    assert session.scalar(select(func.count()).select_from(ExecutionFill)) == 0


def test_stale_revision_rejected_without_overwrite(session: Session):
    append_manual_record(session, _payload())
    session.commit()
    with pytest.raises(ValueError, match="版本冲突"):
        append_manual_record(session, _payload(expected_revision=0))
    assert session.scalar(select(func.count()).select_from(ManualJournalRevision)) == 1


def test_explicit_empty_holdings_and_unknown_funds_can_be_saved(session: Session):
    saved = append_manual_record(session, _payload(
        available_cash=None, total_equity=None, lots=[], operation=None,
    ))
    assert saved["lots"] == []
    assert saved["available_cash"] is None
    assert saved["source"] == "user_manual"


def test_read_response_uses_one_coherent_revision_snapshot(session: Session):
    append_manual_record(session, _payload())
    row = session.scalar(select(ManualJournalRevision))

    class ConcurrentAppendBetweenQueries:
        def scalars(self, _query):
            return [row]

        def scalar(self, _query):
            return 2

    response = read_manual_records(ConcurrentAppendBetweenQueries())
    assert response["latest_revision"] == 1
    assert response["total_revisions"] == 1
    assert len(response["history"]) == 1


def test_new_snapshot_cannot_move_account_observation_backwards(session: Session):
    now = datetime.now(UTC).replace(microsecond=0)
    append_manual_record(session, _payload(observed_at=now))
    session.commit()
    with pytest.raises(ValueError, match="观察时间"):
        append_manual_record(session, _payload(
            expected_revision=1, observed_at=now - timedelta(hours=1),
        ))
    assert session.scalar(select(func.count()).select_from(ManualJournalRevision)) == 1


def test_unknown_old_purchase_time_stays_unknown(session: Session):
    payload = _payload(lots=[{
        "symbol": "600000.SH", "quantity": "100", "paid_amount": None,
        "bought_at": None,
    }])
    lot = append_manual_record(session, payload)["lots"][0]
    assert lot["bought_at"] is None
    assert lot["paid_amount"] is None


def test_exponent_input_is_returned_as_plain_decimal_for_browser_contract(session: Session):
    payload = _payload(lots=[{
        "symbol": "600000.SH", "quantity": "1e2", "paid_amount": "9.8e2",
        "bought_at": None,
    }])
    lot = append_manual_record(session, payload)["lots"][0]
    assert lot["quantity"] == "100"
    assert lot["paid_amount"] == "980"


def test_trailing_zero_input_uses_four_decimal_places_or_fewer(session: Session):
    payload = _payload(lots=[{
        "symbol": "600000.SH", "quantity": "100.00000", "paid_amount": "980.00000",
        "bought_at": None,
    }], operation={
        "side": "BUY", "symbol": "600000.SH", "quantity": "100.00000",
        "price": "9.80000", "fee": "0.00000",
        "executed_at": datetime.now(UTC) - timedelta(minutes=1),
    })
    saved = append_manual_record(session, payload)
    assert saved["lots"][0]["quantity"] == "100"
    assert saved["lots"][0]["paid_amount"] == "980"
    assert saved["operation"]["price"] == "9.8"


def test_buy_operation_adds_a_lot_from_latest_snapshot(session: Session):
    now = datetime.now(UTC).replace(microsecond=0)
    append_manual_record(session, _payload(observed_at=now - timedelta(hours=2)))
    session.commit()
    result = apply_manual_operation(session, ManualOperationApply(
        expected_revision=1, observed_at=now, available_cash=None,
        operation={"side": "BUY", "symbol": "600000.SH", "quantity": "50",
                   "price": "10.25", "fee": "5", "executed_at": now - timedelta(minutes=1)},
    ))
    session.commit()
    assert result["revision"] == 2
    assert len(result["lots"]) == 2
    assert result["lots"][1] == {
        "symbol": "600000.SH", "quantity": "50", "paid_amount": "517.5",
        "bought_at": (now - timedelta(minutes=1)).isoformat(),
    }
    assert result["available_cash"] is None
    assert session.scalar(select(func.count()).select_from(ExecutionFill)) == 0
    assert session.scalar(select(func.count()).select_from(AccountSnapshot)) == 0


def test_buy_without_known_fee_keeps_invested_amount_unknown(session: Session):
    now = datetime.now(UTC).replace(microsecond=0)
    append_manual_record(session, _payload(observed_at=now - timedelta(hours=2)))
    session.commit()
    result = apply_manual_operation(session, ManualOperationApply(
        expected_revision=1, observed_at=now,
        operation={"side": "BUY", "symbol": "000001.SZ", "quantity": "100",
                   "price": "10", "executed_at": now - timedelta(minutes=1)},
    ))
    assert result["lots"][-1]["paid_amount"] is None


def test_signed_zero_fee_is_serialized_as_frontend_readable_zero(session: Session):
    now = datetime.now(UTC).replace(microsecond=0)
    append_manual_record(session, _payload(observed_at=now - timedelta(hours=2)))
    session.commit()
    result = apply_manual_operation(session, ManualOperationApply(
        expected_revision=1, observed_at=now,
        operation={"side": "BUY", "symbol": "000001.SZ", "quantity": "10",
                   "price": "10", "fee": "-0", "executed_at": now - timedelta(minutes=1)},
    ))
    assert result["operation"]["fee"] == "0"


def test_full_sale_removes_selected_lot(session: Session):
    now = datetime.now(UTC).replace(microsecond=0)
    append_manual_record(session, _payload(observed_at=now - timedelta(hours=2)))
    session.commit()
    result = apply_manual_operation(session, ManualOperationApply(
        expected_revision=1, observed_at=now, sell_lot_index=0,
        operation={"side": "SELL", "symbol": "600000.SH", "quantity": "100",
                   "price": "10", "executed_at": now - timedelta(minutes=1)},
    ))
    assert result["lots"] == []


def test_sell_operation_reduces_selected_lot_and_clears_unknown_remaining_cost(session: Session):
    now = datetime.now(UTC).replace(microsecond=0)
    append_manual_record(session, _payload(observed_at=now - timedelta(hours=2)))
    session.commit()
    result = apply_manual_operation(session, ManualOperationApply(
        expected_revision=1, observed_at=now, sell_lot_index=0,
        operation={"side": "SELL", "symbol": "600000.SH", "quantity": "40",
                   "price": "10.25", "executed_at": now - timedelta(minutes=1)},
    ))
    assert result["lots"][0]["quantity"] == "60"
    assert result["lots"][0]["paid_amount"] is None
    assert result["lots"][0]["bought_at"] is not None
    assert result["broker_reconciled"] is False


def test_one_sale_can_reduce_multiple_buy_lots_atomically(session: Session):
    now = datetime.now(UTC).replace(microsecond=0)
    append_manual_record(session, _payload(observed_at=now - timedelta(hours=2), lots=[
        {"symbol": "600000.SH", "quantity": "50", "paid_amount": "500"},
        {"symbol": "000001.SZ", "quantity": "10", "paid_amount": "100"},
        {"symbol": "600000.SH", "quantity": "40", "paid_amount": "400"},
    ]))
    session.commit()
    result = apply_manual_operation(session, ManualOperationApply(
        expected_revision=1, observed_at=now,
        sell_allocations=[{"lot_index": 0, "quantity": "30"},
                          {"lot_index": 2, "quantity": "40"}],
        operation={"side": "SELL", "symbol": "600000.SH", "quantity": "70",
                   "price": "10", "executed_at": now - timedelta(minutes=1)},
    ))
    assert [(lot["symbol"], lot["quantity"]) for lot in result["lots"]] == [
        ("600000.SH", "20"), ("000001.SZ", "10")]
    assert result["lots"][0]["paid_amount"] is None
    assert result["operation"]["quantity"] == "70"


def test_two_backfilled_trades_can_be_entered_in_execution_order_after_close(session: Session):
    now = datetime.now(UTC).replace(microsecond=0)
    append_manual_record(session, _payload(observed_at=now - timedelta(days=1)))
    session.commit()
    for revision, minutes_before in ((1, 120), (2, 60)):
        result = apply_manual_operation(session, ManualOperationApply(
            expected_revision=revision, observed_at=now,
            operation={"side": "BUY", "symbol": "000001.SZ", "quantity": "10",
                       "price": "10", "executed_at": now - timedelta(minutes=minutes_before)},
        ))
        session.commit()
    assert result["revision"] == 3
    assert [lot["quantity"] for lot in result["lots"] if lot["symbol"] == "000001.SZ"] == [
        "10", "10"]


@pytest.mark.parametrize("allocations", [
    [{"lot_index": 0, "quantity": "39"}],
    [{"lot_index": 0, "quantity": "20"}, {"lot_index": 0, "quantity": "20"}],
    [{"lot_index": 0, "quantity": "20"}, {"lot_index": 99, "quantity": "20"}],
])
def test_sale_rejects_allocations_with_wrong_total_or_duplicate_or_missing_lot(
    session: Session, allocations,
):
    now = datetime.now(UTC).replace(microsecond=0)
    append_manual_record(session, _payload(observed_at=now - timedelta(hours=2)))
    session.commit()
    with pytest.raises(ValueError):
        apply_manual_operation(session, ManualOperationApply(
            expected_revision=1, observed_at=now, sell_allocations=allocations,
            operation={"side": "SELL", "symbol": "600000.SH", "quantity": "40",
                       "price": "10", "executed_at": now - timedelta(minutes=1)},
        ))
    assert session.scalar(select(func.count()).select_from(ManualJournalRevision)) == 1


@pytest.mark.parametrize("side,index,quantity,symbol,minutes_before", [
    ("SELL", None, "1", "600000.SH", 1),
    ("SELL", 0, "101", "600000.SH", 1),
    ("SELL", 0, "1", "000001.SZ", 1),
    ("SELL", 2, "1", "600000.SH", 1),
    ("BUY", 0, "1", "600000.SH", 1),
    ("BUY", None, "1", "600000.SH", 180),
])
def test_operation_rejects_ambiguous_lot_or_prebaseline_execution(
    session: Session, side, index, quantity, symbol, minutes_before,
):
    now = datetime.now(UTC).replace(microsecond=0)
    append_manual_record(session, _payload(observed_at=now - timedelta(hours=2)))
    session.commit()
    payload = ManualOperationApply(
        expected_revision=1, observed_at=now, sell_lot_index=index,
        operation={"side": side, "symbol": symbol, "quantity": quantity,
                   "price": "10", "executed_at": now - timedelta(minutes=minutes_before)},
    )
    with pytest.raises(ValueError):
        apply_manual_operation(session, payload)
    assert session.scalar(select(func.count()).select_from(ManualJournalRevision)) == 1


@pytest.mark.parametrize("changes", [
    {"available_cash": "NaN"},
    {"available_cash": "-1"},
    {"observed_at": datetime.now(UTC) + timedelta(days=1)},
    {"observed_at": datetime.now(UTC).replace(tzinfo=None)},
    {"lots": [{"symbol": "600000.SH", "quantity": "0", "paid_amount": "9",
               "bought_at": datetime.now(UTC)}]},
    {"lots": [{"symbol": "600000.SH", "quantity": "1", "paid_amount": "-9",
               "bought_at": datetime.now(UTC)}]},
    {"operation": {"side": "BUY", "symbol": "600000.SH", "quantity": "1",
                   "price": "9", "executed_at": datetime.now(UTC) + timedelta(days=1)}},
])
def test_invalid_self_report_rejected(changes):
    with pytest.raises(ValidationError):
        _payload(**changes)
