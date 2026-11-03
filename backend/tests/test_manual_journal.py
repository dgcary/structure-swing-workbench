"""A manual journal is a versioned self-report, never a formal broker fact."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import AccountSnapshot, ExecutionFill, ManualJournalRevision
from app.workbench.manual_journal import (
    ManualJournalWrite,
    append_manual_record,
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


@pytest.mark.parametrize("changes", [
    {"available_cash": "NaN"},
    {"available_cash": "-1"},
    {"available_cash": None, "total_equity": None, "lots": [], "operation": None},
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
