"""Reverse-T maximum exposure is illustrative until broker and T+1 reconciliation."""

from decimal import Decimal

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
    assert risk["existing_t_max_loss"] == "0"
    assert risk["other_positions_max_loss"] == "100"
    assert risk["projected_max_loss"] == "400.0"
    assert Decimal(risk["projected_account_risk_pct"]) == Decimal("1.6")
    assert risk["account_total_max_loss"] == "500.0"
    assert Decimal(risk["account_total_risk_pct"]) == Decimal("2")
    assert risk["level"] == "PASS"
    assert risk["verified"] is False
    assert risk["source"] == "用户手工假设"
    assert body["broker_reconciled"] is False
    assert body["trade_execution_enabled"] is False

    # A same-day sell leg never erases peak intraday exposure.
    closed = preview(close_quantity="100", close_price="11").json()
    assert closed["cycle_status"] == "closed"
    assert closed["projected_risk"] == risk


def test_reverse_t_risk_levels_use_confirmed_two_and_three_percent_boundaries():
    at_two = preview(risk_inputs={**RISK, "account_equity": "20000"}).json()
    assert Decimal(at_two["projected_risk"]["projected_account_risk_pct"]) == Decimal(2)
    assert at_two["projected_risk"]["level"] == "PASS"

    warning = preview(risk_inputs={**RISK, "account_equity": "16000"}).json()
    assert Decimal(warning["projected_risk"]["projected_account_risk_pct"]) == Decimal("2.5")
    assert warning["projected_risk"]["level"] == "WARNING"

    at_three = preview(risk_inputs={
        **RISK, "account_equity": "20000", "existing_t_max_loss": "200",
    }).json()
    assert Decimal(at_three["projected_risk"]["projected_account_risk_pct"]) == Decimal(3)
    assert at_three["projected_risk"]["level"] == "WARNING"
    assert Decimal(at_three["projected_risk"]["account_total_risk_pct"]) == Decimal("3.5")

    over_three = preview(risk_inputs={**RISK, "account_equity": "10000"}).json()
    assert over_three["projected_risk"]["level"] == "HARD_FAIL"
    assert Decimal(over_three["projected_risk"]["projected_account_risk_pct"]) == Decimal(4)
    assert over_three["trade_execution_enabled"] is False


def test_other_stocks_cannot_trigger_a_new_account_level_hard_fail():
    # §15.63: 1.1% for this plan, 3.6% across stocks, no account-level gate.
    risk = preview(open_quantity="100", open_price="10", risk_inputs={
        **RISK,
        "account_equity": "100000",
        "core_quantity": "1000",
        "core_cost_price": "10",
        "main_invalidation_price": "9",
        "t_stop_price": "9",
        "other_positions_max_loss": "2500",
    }).json()["projected_risk"]
    assert risk["projected_max_loss"] == "1100"
    assert Decimal(risk["projected_account_risk_pct"]) == Decimal("1.1")
    assert risk["level"] == "PASS"
    assert risk["account_total_max_loss"] == "3600"
    assert Decimal(risk["account_total_risk_pct"]) == Decimal("3.6")
    assert risk["verified"] is False


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


def test_extreme_finite_reverse_t_risk_assumptions_return_422_not_server_error():
    """Pydantic must reject exponent overflow before Decimal risk arithmetic."""
    for field in RISK:
        for invalid in ("1e999999", "1e-999999"):
            response = preview(risk_inputs={**RISK, field: invalid})
            assert response.status_code == 422, (field, invalid, response.text)
    for field in ("core_cost_price", "main_invalidation_price", "t_stop_price"):
        response = preview(risk_inputs={**RISK, field: "100000000000000"})
        assert response.status_code == 422, (field, response.text)
    # DB-compatible four-place prices and quantities still produce a preview.
    ok = preview(open_quantity="100.0000", open_price="10.0000",
                 risk_inputs={**RISK, "t_stop_price": "9.5000"})
    assert ok.status_code == 200
    assert ok.json()["projected_risk"]["verified"] is False
    assert ok.json()["trade_execution_enabled"] is False


def test_large_valid_reverse_t_inputs_preserve_fractional_risk():
    result = preview(risk_inputs={
        **RISK,
        "account_equity": "9999999999999999.9999",
        "core_quantity": "9999999999999999.9999",
        "core_cost_price": "99999999999999.9999",
        "main_invalidation_price": "99999999999999.9998",
        "existing_t_max_loss": "0",
        "other_positions_max_loss": "0",
    })
    assert result.status_code == 200
    risk = result.json()["projected_risk"]
    assert risk["core_max_loss"] == "999999999999.99999999"
    assert risk["projected_max_loss"] == "1000000000049.99999999"
    assert risk["account_total_max_loss"] == "1000000000049.99999999"
    assert risk["verified"] is False
