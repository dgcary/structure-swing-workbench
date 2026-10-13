"""Manual account corrections must be all-or-nothing."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.account import AccountLedger, correct_account, correct_holding


def test_invalid_second_account_field_does_not_write_first() -> None:
    ledger = AccountLedger()
    with pytest.raises(ValueError, match="有限非负数"):
        correct_account(
            ledger, equity=Decimal("10000"), cash=Decimal("-1"),
            at=datetime(2026, 10, 14, tzinfo=UTC), source_id="manual",
        )
    assert ledger.facts == {}
    assert ledger.audit == []
    assert ledger.conflicts == []


def test_invalid_second_holding_field_does_not_write_first() -> None:
    ledger = AccountLedger()
    with pytest.raises(ValueError, match="有限非负数"):
        correct_holding(
            ledger, symbol="TEST", quantity=Decimal("100"), cost=Decimal("NaN"),
            at=datetime(2026, 10, 14, tzinfo=UTC), source_id="manual",
        )
    assert ledger.facts == {}
    assert ledger.audit == []
    assert ledger.conflicts == []
