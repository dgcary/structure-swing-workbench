"""M8 manual-only plan preview contract and fail-closed boundary tests."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def payload(**changes: object) -> dict[str, object]:
    fields: dict[str, object] = {
        "symbol": "600000",
        "account_equity": "100000",
        "planned_quantity": "1000",
        "planned_entry_price": "10",
        "invalidation_price": "9",
        "initial_pct": "40",
        "confirmation_pct": "30",
        "t_reserve_pct": "30",
        "action_type": "initial_entry",
        "structure_invalidated": False,
    }
    fields.update(changes)
    return fields


def test_preview_is_never_formal_approval() -> None:
    response = client.post("/workbench/plan-preview", json=payload())
    assert response.status_code == 200
    result = response.json()
    assert result["mode"] == "partial_preview"
    assert result["input_source"] == "user"
    assert result["persisted"] is False
    assert result["formal_audit_completed"] is False
    assert result["executable"] is False
    assert result["trade_execution_enabled"] is False
    assert result["account_risk_pct"] == "1.00"


def test_structure_invalidated_buy_is_hard_fail() -> None:
    response = client.post(
        "/workbench/plan-preview",
        json=payload(structure_invalidated=True, action_type="reverse_t_buy"),
    )
    assert response.status_code == 200
    result = response.json()
    assert result["highest_checked_level"] == "hard_fail"
    assert result["findings"][0]["rule"] == "structure_invalidation"
    assert result["executable"] is False


def test_risk_above_three_percent_is_hard_fail() -> None:
    response = client.post(
        "/workbench/plan-preview",
        json=payload(planned_quantity="4000"),
    )
    assert response.status_code == 200
    assert response.json()["highest_checked_level"] == "hard_fail"


def test_risk_between_two_and_three_percent_is_warning() -> None:
    response = client.post(
        "/workbench/plan-preview",
        json=payload(planned_quantity="2500"),
    )
    assert response.status_code == 200
    assert response.json()["highest_checked_level"] == "warning"


def test_invalid_or_missing_user_input_is_rejected() -> None:
    invalid = [
        payload(symbol="60000"),
        payload(account_equity="0"),
        payload(invalidation_price="10"),
        payload(initial_pct="50"),
        payload(action_type="not_an_action"),
    ]
    for fields in invalid:
        response = client.post("/workbench/plan-preview", json=fields)
        assert response.status_code == 422
    missing = payload()
    del missing["structure_invalidated"]
    assert client.post("/workbench/plan-preview", json=missing).status_code == 422
