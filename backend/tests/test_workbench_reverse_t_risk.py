"""Reverse-T maximum exposure is illustrative until broker and T+1 reconciliation."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

RISK = {
    "account_equity": "25000",
    "core_quantity": "700",
    "core_cost_price": "10",
    "main_invalidation_price": "9.5",
    "t_stop_price": "9.5",
    "existing_t_max_loss": "0",
    "other_positions_max_loss": "100",
}


def preview(**changes):
    payload = {
        "symbol": "600000",
        "direction": "reverse",
        "open_quantity": "100",
        "open_price": "10",
        "close_quantity": "0",
        "close_price": None,
        "risk_inputs": RISK,
    }
    payload.update(changes)
    return client.post("/workbench/t-cycle-preview", json=payload)


def test_reverse_t_risk_uses_peak_inventory_and_separate_stops():
    response = preview()
    assert response.status_code == 200
    body = response.json()
    risk = body["projected_risk"]
    assert risk["core_max_loss"] == "350.0"
    assert risk["new_t_max_loss"] == "50.0"
    assert risk["projected_max_loss"] == "500.0"
    assert risk["projected_account_risk_pct"] == "2.000"
    assert risk["level"] == "PASS"
    assert risk["verified"] is False
    assert risk["source"] == "用户手工假设"
    assert body["broker_reconciled"] is False
    assert body["trade_execution_enabled"] is False

    # Even a completed same-day sell leg does not erase peak intraday risk.
    closed = preview(close_quantity="100", close_price="11").json()
    assert closed["cycle_status"] == "closed"
    assert closed["projected_risk"] == risk


def test_reverse_t_risk_levels_use_confirmed_two_and_three_percent_boundaries():
    warning = preview(risk_inputs={**RISK, "account_equity": "20000"}).json()
    assert warning["projected_risk"]["level"] == "WARNING"
    assert warning["projected_risk"]["projected_account_risk_pct"] == "2.500"
    at_three = preview(risk_inputs={**RISK, "account_equity": "16666.6666666667"}).json()
    assert at_three["projected_risk"]["level"] == "WARNING"
    over_three = preview(risk_inputs={**RISK, "account_equity": "10000"}).json()
    assert over_three["projected_risk"]["level"] == "HARD_FAIL"
    assert over_three["trade_execution_enabled"] is False


def test_missing_or_untrusted_risk_assumptions_never_become_verified():
    assert preview(risk_inputs=None).json()["projected_risk"] is None
    for invalid in (
        {"risk_inputs": {key: value for key, value in RISK.items()
                         if key != "existing_t_max_loss"}},
        {"risk_inputs": {**RISK, "t_stop_price": "10"}},
        {"risk_inputs": {**RISK, "t_stop_price": "11"}},
        {"risk_inputs": {**RISK, "other_positions_max_loss": "-1"}},
        {"risk_inputs": {**RISK, "account_equity": "0"}},
        {"risk_inputs": {**RISK, "core_quantity": "NaN"}},
        {"risk_inputs": {**RISK, "existing_t_max_loss": "Infinity"}},
        {"direction": "positive"},
    ):
        assert preview(**invalid).status_code == 422, invalid
