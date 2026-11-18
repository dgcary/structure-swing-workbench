"""Plan review API tests: planned vs actual fills."""

from __future__ import annotations

from fastapi.testclient import TestClient
from test_api_plans import _audit_version, _create_plan, _decide, _submit


def _effective_plan(client: TestClient) -> dict:
    plan = _create_plan(client)
    version_id = plan["versions"][0]["id"]
    _submit(client, version_id)
    _audit_version(client, version_id)
    _decide(client, version_id, approve=True)
    return client.get(f"/plans/{plan['id']}").json()


def _action(
    client: TestClient,
    version_id: str,
    action_type: str,
    side: str,
    qty: str,
    low: str = "10.00",
    high: str = "10.50",
) -> dict:
    response = client.post(
        f"/plan-versions/{version_id}/actions",
        json={
            "action_type": action_type,
            "side": side,
            "planned_price_low": low,
            "planned_price_high": high,
            "planned_quantity": qty,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _fill(client: TestClient, action_id: str, price: str, quantity: str, at: str) -> None:
    response = client.post(
        f"/actions/{action_id}/fills",
        json={"quantity": quantity, "price": price, "executed_at": at},
    )
    assert response.status_code == 201, response.text


def test_review_with_entry_and_partial_exit(api_client: TestClient) -> None:
    plan = _effective_plan(api_client)
    version_id = plan["effective_version_id"]
    entry = _action(api_client, version_id, "initial_entry", "buy", "1000")
    _fill(api_client, entry["id"], "10.20", "1000", "2026-11-10T14:30:00+08:00")
    reduce_action = _action(api_client, version_id, "reduce", "sell", "500", low="10.50", high="11.20")
    _fill(api_client, reduce_action["id"], "11.00", "500", "2026-11-17T14:30:00+08:00")

    review = api_client.get(f"/plans/{plan['id']}/review").json()
    data = review["review"]
    assert data["total_buy_quantity"] == "1000.0000"
    assert data["total_sell_quantity"] == "500.0000"
    assert data["avg_buy_price"] == "10.2000"
    assert data["avg_sell_price"] == "11.0000"
    # 毛盈亏 =（11.00 − 10.20）× 500
    assert data["realized_gross_pnl"] == "400.0000"
    assert data["remaining_quantity"] == "500.0000"
    # 实际建仓 10.20 对计划下沿 10.00 的偏差
    assert data["entry_deviation_pct"] == "2.0000"
    assert data["holding_days"] == 7
    assert data["long_holding_note"] is None
    assert review["audit_summary"]


def test_review_without_fills_returns_empty_state(api_client: TestClient) -> None:
    plan = _effective_plan(api_client)
    review = api_client.get(f"/plans/{plan['id']}/review").json()
    data = review["review"]
    assert data["total_buy_quantity"] == "0.0000"
    assert data["realized_gross_pnl"] == "0.0000"
    assert data["avg_buy_price"] is None
    assert data["first_fill_at"] is None
    assert data["holding_days"] is None


def test_review_flags_long_holding(api_client: TestClient) -> None:
    plan = _effective_plan(api_client)
    version_id = plan["effective_version_id"]
    entry = _action(api_client, version_id, "initial_entry", "buy", "1000")
    _fill(api_client, entry["id"], "10.10", "1000", "2026-11-01T14:30:00+08:00")
    reduce_action = _action(api_client, version_id, "reduce", "sell", "1000")
    _fill(api_client, reduce_action["id"], "10.40", "1000", "2026-11-18T14:30:00+08:00")

    review = api_client.get(f"/plans/{plan['id']}/review").json()
    data = review["review"]
    assert data["holding_days"] == 17
    assert data["long_holding_note"] is not None
    assert "不构成违规" in data["long_holding_note"]


def test_review_unknown_plan_404(api_client: TestClient) -> None:
    response = api_client.get("/plans/does-not-exist/review")
    assert response.status_code == 404
