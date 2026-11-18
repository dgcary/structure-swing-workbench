"""T-cycle grouping view API tests."""

from __future__ import annotations

from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from test_api_plans import _audit_version, _create_plan, _decide, _submit

CHINA = ZoneInfo("Asia/Shanghai")
DAY = "2026-11-18"


def _effective_plan(client: TestClient) -> dict:
    plan = _create_plan(client)
    version_id = plan["versions"][0]["id"]
    _submit(client, version_id)
    _audit_version(client, version_id)
    _decide(client, version_id, approve=True)
    return client.get(f"/plans/{plan['id']}").json()


def _t_action(client: TestClient, version_id: str, action_type: str, side: str, key: str) -> dict:
    response = client.post(
        f"/plan-versions/{version_id}/actions",
        json={
            "action_type": action_type,
            "side": side,
            "t_cycle_key": key,
            "planned_price_low": "10.00",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _t_fill(client: TestClient, action_id: str, price: str, quantity: str = "500") -> None:
    response = client.post(
        f"/actions/{action_id}/fills",
        json={
            "quantity": quantity,
            "price": price,
            "executed_at": f"{DAY}T14:30:00+08:00",
        },
    )
    assert response.status_code == 201, response.text


def test_completed_t_cycle_groups_and_pnl(api_client: TestClient) -> None:
    plan = _effective_plan(api_client)
    version_id = plan["effective_version_id"]
    sell = _t_action(api_client, version_id, "positive_t_sell", "sell", "T1")
    buyback = _t_action(api_client, version_id, "positive_t_buyback", "buy", "T1")
    _t_fill(api_client, sell["id"], "10.50")
    _t_fill(api_client, buyback["id"], "10.20")

    cycles = api_client.get("/t-cycles").json()
    assert len(cycles) == 1
    cycle = cycles[0]
    assert cycle["t_cycle_key"] == "T1"
    assert cycle["instrument_code"] == "600000"
    assert cycle["status"] == "已完成"
    assert cycle["matched_quantity"] == "500.0000"
    # 毛盈亏 =（卖价 − 买价）× 数量 = 0.30 × 500
    assert cycle["matched_gross_pnl"] == "150.0000"
    assert cycle["remaining_quantity"] == "0.0000"
    assert cycle["day"] == DAY
    assert cycle["exceeds_daily_limit"] is False


def test_open_t_cycle_shows_remaining(api_client: TestClient) -> None:
    plan = _effective_plan(api_client)
    version_id = plan["effective_version_id"]
    sell = _t_action(api_client, version_id, "positive_t_sell", "sell", "T1")
    _t_fill(api_client, sell["id"], "10.50")

    cycles = api_client.get("/t-cycles").json()
    assert len(cycles) == 1
    cycle = cycles[0]
    assert cycle["status"] == "进行中"
    assert cycle["remaining_quantity"] == "500.0000"
    assert cycle["open_side"]["label"] == "卖出"
    assert cycle["matched_gross_pnl"] == "0.0000"


def test_cycles_are_grouped_per_instrument_and_day_limit(api_client: TestClient) -> None:
    plan = _effective_plan(api_client)
    version_id = plan["effective_version_id"]
    for key in ("T1", "T2", "T3"):
        sell = _t_action(api_client, version_id, "positive_t_sell", "sell", key)
        buyback = _t_action(api_client, version_id, "positive_t_buyback", "buy", key)
        _t_fill(api_client, sell["id"], "10.50")
        _t_fill(api_client, buyback["id"], "10.20")

    cycles = api_client.get("/t-cycles").json()
    assert len(cycles) == 3
    assert all(item["exceeds_daily_limit"] is True for item in cycles)


def test_t_cycle_filter_by_instrument(api_client: TestClient) -> None:
    plan = _effective_plan(api_client)
    version_id = plan["effective_version_id"]
    sell = _t_action(api_client, version_id, "positive_t_sell", "sell", "T1")
    _t_fill(api_client, sell["id"], "10.50")

    filtered = api_client.get("/t-cycles?instrument_code=600000").json()
    assert len(filtered) == 1
    none = api_client.get("/t-cycles?instrument_code=000001").json()
    assert none == []
