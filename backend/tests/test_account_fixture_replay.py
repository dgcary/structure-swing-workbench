"""M5 fixture replay and snapshot/confirmed-fill reconciliation."""

from decimal import Decimal
from pathlib import Path

from app.account import AccountLedger, import_csv, position_view

FIXTURES = Path(__file__).parent / "fixtures"


def test_fixture_replay() -> None:
    book = AccountLedger()
    holdings = (FIXTURES / "m5_holdings.csv").read_text(encoding="utf-8")
    trades = (FIXTURES / "m5_fills.csv").read_text(encoding="utf-8")
    assert import_csv(book, "holdings", holdings, batch_id="baseline").imported == 2
    assert import_csv(book, "fills", trades, batch_id="events").imported == 1
    view = position_view(book, "TEST")
    assert view.quantity == Decimal(210)
    assert view.broker_display_cost is None
    assert view.applied_fill_ids == ("E001",)
    assert import_csv(book, "fills", trades, batch_id="events").batch_duplicate
