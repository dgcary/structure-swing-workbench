"""Execution action and fill recording API tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from tests.test_api_account import _create_snapshot
from tests.test_api_plans import (
    _audit_version,
    _create_plan,
    _decide,
    _submit,
)

CHINA = ZoneInfo("Asia/Shanghai")


def _effective_plan(client: TestClient, **version_overrides: object) -> dict:
    plan = _create_plan(client, **version_overrides)
    version_id = plan["versions"][0]["id"]
    _submit(client, version_id)
    _audit_version(client, version_id)
    _decide(client, version_id, approve=True)
    return client.get(f"/plans/{plan['id']}").json()


def _create_action(client: TestClient, version_id: str, **body: object) -> object:
    payload = {
        "action_type": "initial_entry",
        "side": "buy",
        "planned_price_low": "10.00",
        "planned_price_high": "10.50",
        "planned_quantity": "1000",
        **body,
    }
    return client.post(f"/plan-versions/{version_id}/actions", json=payload)


def _fill(
    client: TestClient, action_id: str, price: str, quantity: str = "1000", **extra: object
) -> object:
    payload = {
        "quantity": quantity,
        "price": price,
        "executed_at": (datetime.now(CHINA) + timedelta(hours=1)).isoformat(),
        **extra,
    }
    return client.post(f"/actions/{action_id}/fills", json=payload)


def test_create_action_on_effective_version(api_client: TestClient) -> None:
    plan = _effective_plan(api_client)
    response = _create_action(api_client, plan["effective_version_id"])
    assert response.status_code == 201, response.text
    action = response.json()
    assert action["action_type"]["label"] == "初始建仓"
    assert action["side"]["label"] == "买入"
    assert action["status"]["label"] == "计划中"
    assert action["plan"]["instrument_code"] == "600000"


def test_create_action_requires_effective_version(api_client: TestClient) -> None:
    plan = _create_plan(api_client)
    response = _create_action(api_client, plan["versions"][0]["id"])
    assert response.status_code == 409
    assert "生效" in response.json()["detail"]


def test_create_action_rejects_side_mismatch(api_client: TestClient) -> None:
    plan = _effective_plan(api_client)
    response = _create_action(
        api_client, plan["effective_version_id"], side="sell"
    )
    assert response.status_code == 409
    assert "方向" in response.json()["detail"]


def test_action_audit_passes_and_marks_audited(api_client: TestClient) -> None:
    plan = _effective_plan(api_client)
    action = _create_action(api_client, plan["effective_version_id"]).json()
    response = api_client.post(f"/actions/{action['id']}/audit")
    assert response.status_code == 200, response.text
    audit = response.json()
    assert audit["level"]["value"] == "pass"
    rules = {finding["rule"] for finding in audit["details"]["findings"]}
    assert {"structure_invalidation", "initial_entry"} <= rules

    detail = api_client.get(f"/actions/{action['id']}").json()
    assert detail["status"]["label"] == "已审计"


def test_fill_records_and_updates_status(api_client: TestClient) -> None:
    plan = _effective_plan(api_client)
    action = _create_action(api_client, plan["effective_version_id"]).json()

    first = _fill(api_client, action["id"], "10.20", quantity="600")
    assert first.status_code == 201, first.text
    payload = first.json()
    assert payload["action"]["status"]["label"] == "部分成交"
    assert payload["audit_result"]["level"]["value"] == "pass"

    second = _fill(api_client, action["id"], "10.30", quantity="400")
    assert second.status_code == 201, second.text
    assert second.json()["action"]["status"]["label"] == "已完成"


def test_fill_out_of_bounds_requires_override(api_client: TestClient) -> None:
    # 计划上沿 10.50；成交 10.60 越界 0.95%，构成可覆盖失败
    plan = _effective_plan(api_client)
    action = _create_action(api_client, plan["effective_version_id"]).json()

    blocked = _fill(api_client, action["id"], "10.60")
    assert blocked.status_code == 409
    assert "覆盖理由" in blocked.json()["detail"]

    allowed = _fill(
        api_client,
        action["id"],
        "10.60",
        override_confirmed=True,
        override_reason="开盘抢筹，接受小幅越界",
    )
    assert allowed.status_code == 201, allowed.text
    audit = allowed.json()["audit_result"]
    assert audit["level"]["value"] == "overridable_fail"
    assert audit["overrides"][0]["reason"] == "开盘抢筹，接受小幅越界"


def test_fill_beyond_one_percent_is_hard_rejected(api_client: TestClient) -> None:
    # 成交 10.70 越界 1.9%，硬性失败不可录入
    plan = _effective_plan(api_client)
    action = _create_action(api_client, plan["effective_version_id"]).json()

    response = _fill(api_client, action["id"], "10.70")
    assert response.status_code == 409
    assert "硬性失败" in response.json()["detail"]

    listing = api_client.get("/actions?status=planned").json()
    assert [item["id"] for item in listing] == [action["id"]]


def test_fill_side_mismatch_rejected(api_client: TestClient) -> None:
    plan = _effective_plan(api_client)
    action = _create_action(api_client, plan["effective_version_id"]).json()
    response = client_sell_fill(api_client, action["id"])
    assert response.status_code == 409
    assert "方向" in response.json()["detail"]


def client_sell_fill(client: TestClient, action_id: str) -> object:
    payload = {
        "side": "sell",
        "quantity": "100",
        "price": "10.20",
        "executed_at": (datetime.now(CHINA) + timedelta(hours=1)).isoformat(),
    }
    return client.post(f"/actions/{action_id}/fills", json=payload)


def test_fill_rejected_after_structure_invalidation(api_client: TestClient) -> None:
    plan = _effective_plan(api_client, structure_invalidated=True)
    action = _create_action(api_client, plan["effective_version_id"]).json()

    audit_response = api_client.post(f"/actions/{action['id']}/audit")
    assert audit_response.json()["level"]["value"] == "hard_fail"

    detail = api_client.get(f"/actions/{action['id']}").json()
    assert detail["status"]["label"] == "计划中"

    response = _fill(api_client, action["id"], "10.20")
    assert response.status_code == 409
    assert "硬性失败" in response.json()["detail"]


def test_cancel_action(api_client: TestClient) -> None:
    plan = _effective_plan(api_client)
    action = _create_action(api_client, plan["effective_version_id"]).json()
    response = api_client.patch(f"/actions/{action['id']}/cancel")
    assert response.status_code == 200
    assert response.json()["status"]["label"] == "已取消"


def test_overview_positions_reflect_fills(api_client: TestClient) -> None:
    _create_snapshot(api_client)  # 基准快照：600000 持仓 10000
    plan = _effective_plan(api_client)
    action = _create_action(api_client, plan["effective_version_id"]).json()
    first = _fill(api_client, action["id"], "10.20", quantity="600")
    assert first.status_code == 201

    overview = api_client.get("/account/overview").json()
    positions = {
        item["instrument_code"]: item for item in overview["current_positions"]
    }
    position = positions["600000"]
    assert position["baseline_quantity"] == "10000.0000"
    assert position["net_fill_delta"] == "600.0000"
    assert position["current_quantity"] == "10600.0000"
