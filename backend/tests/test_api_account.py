"""Account snapshot and overview API tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from test_api_plans import EQUITY, PASSING_VERSION, _audit_version, _decide, _submit

CHINA = ZoneInfo("Asia/Shanghai")


def _create_snapshot(client: TestClient, *, equity: str = EQUITY) -> dict:
    payload = {
        "captured_at": datetime.now(CHINA).isoformat(),
        "total_equity": equity,
        "available_cash": "500000",
        "source": "manual",
        "positions": [
            {
                "instrument_code": "600000",
                "instrument_name": "浦发银行",
                "total_quantity": "10000",
                "market_value": "105000",
                "broker_cost_price": "10.20",
                "buckets": [
                    {
                        "bucket_type": "core",
                        "quantity": "10000",
                        "strategy_cost_price": "10.20",
                        "effective_cost_price": "10.10",
                        "realized_t_pnl": "0",
                    }
                ],
            }
        ],
    }
    response = client.post("/account/snapshots", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_snapshot_with_positions_and_buckets(api_client: TestClient) -> None:
    snapshot = _create_snapshot(api_client)
    assert snapshot["total_equity"] == "1000000.0000"
    assert len(snapshot["positions"]) == 1
    position = snapshot["positions"][0]
    assert position["instrument_code"] == "600000"
    assert position["buckets"][0]["bucket_type"]["label"] == "核心仓"
    assert position["buckets"][0]["effective_cost_price"] == "10.1000"


def test_list_snapshots_orders_by_time_desc(api_client: TestClient) -> None:
    first = _create_snapshot(api_client)
    later_payload = {
        "captured_at": (datetime.now(CHINA) + timedelta(hours=1)).isoformat(),
        "total_equity": "1100000",
        "available_cash": "600000",
        "positions": [],
    }
    second = api_client.post("/account/snapshots", json=later_payload)
    assert second.status_code == 201
    listing = api_client.get("/account/snapshots").json()
    assert [item["id"] for item in listing] == [second.json()["id"], first["id"]]
    assert listing[0]["total_equity"] == "1100000.0000"


def test_overview_without_data_returns_empty_state(api_client: TestClient) -> None:
    overview = api_client.get("/account/overview").json()
    assert overview["snapshot"] is None
    assert overview["active_plan_count"] == 0
    assert overview["position_count"] == 0
    assert overview["total_risk_pct"] is None


def test_overview_includes_active_plan_and_risk(api_client: TestClient) -> None:
    _create_snapshot(api_client)
    payload = {
        "instrument_code": "600000",
        "instrument_name": "浦发银行",
        "account_equity": EQUITY,
        "version": PASSING_VERSION,
    }
    plan = api_client.post("/plans", json=payload).json()
    version_id = plan["versions"][0]["id"]
    _submit(api_client, version_id)
    _audit_version(api_client, version_id)
    _decide(api_client, version_id, approve=True)

    overview = api_client.get("/account/overview").json()
    assert overview["active_plan_count"] == 1
    assert overview["position_count"] == 1
    assert overview["total_risk_pct"] == "1.2000"
    active = overview["active_plans"][0]
    assert active["instrument_code"] == "600000"
    assert active["risk_pct"] == "1.2000"
    assert overview["snapshot"]["total_equity"] == "1000000.0000"
