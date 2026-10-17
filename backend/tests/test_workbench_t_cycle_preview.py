"""Manual T-cycle preview is an isolated calculation, not an execution signal."""
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def call(**changes):
    data = dict(symbol="600000", direction="positive", open_quantity="100",
                open_price="12", close_quantity="100", close_price="10")
    data.update(changes)
    return client.post("/workbench/t-cycle-preview", json=data)


def test_closed_cycles():
    result = call()
    assert result.status_code == 200
    body = result.json()
    assert body["realized_gross_pnl"] == "200"
    assert body["cycle_status"] == "closed"
    assert body["remaining_quantity"] == "0"
    for flag in ("persisted", "broker_reconciled",
                 "daily_cycle_limit_verified", "trade_execution_enabled"):
        assert body[flag] is False
    reverse = call(direction="reverse", open_price="10", close_price="11")
    assert reverse.status_code == 200
    assert reverse.json()["realized_gross_pnl"] == "100"


def test_partial_and_open_cycles():
    partial = call(close_quantity="40").json()
    assert partial["cycle_status"] == "open"
    assert partial["remaining_quantity"] == "60"
    assert partial["realized_gross_pnl"] is None
    assert partial["pending_matched_gross_pnl"] == "80"
    empty = call(close_quantity="0", close_price=None).json()
    assert empty["remaining_quantity"] == "100"
    assert empty["realized_gross_pnl"] is None
    assert empty["trade_execution_enabled"] is False


def test_invalid_input():
    assert call(close_price="13").json()["realized_gross_pnl"] == "-100"
    for invalid in (
        {"symbol": "123"}, {"direction": "other"}, {"open_quantity": "0"},
        {"open_price": "-1"}, {"close_quantity": "101"},
        {"close_quantity": "0", "close_price": "10"},
        {"close_quantity": "10", "close_price": None},
        {"open_price": "NaN"}, {"open_quantity": "Infinity"},
    ):
        assert call(**invalid).status_code == 422, invalid
