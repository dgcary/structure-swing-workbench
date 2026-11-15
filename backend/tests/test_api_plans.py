"""Plan lifecycle, version audit and override API tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

PASSING_VERSION = {
    "setup_type": "c",
    "structure_stage": "early",
    "entry_mode": "price_range",
    "planned_total_position_pct": "30",
    "initial_entry_price_low": "10.00",
    "initial_entry_price_high": "10.50",
    "structure_invalidation_price": "9.60",
    "structure_invalidation_condition": "跌破9.60视为结构失效",
    "initial_entry_pct": "40",
    "confirmation_add_pct": "30",
    "t_reserve_pct": "30",
    "first_target_price": "11.50",
    "first_target_type": "prior_high",
    "first_target_reduce_pct": "50",
}

EQUITY = "1000000"


def _create_plan(client: TestClient, **version_overrides: object) -> dict:
    payload = {
        "instrument_code": "600000",
        "instrument_name": "浦发银行",
        "account_equity": EQUITY,
        "version": {**PASSING_VERSION, **version_overrides},
    }
    response = client.post("/plans", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _audit_version(client: TestClient, version_id: str, equity: str = EQUITY) -> dict:
    response = client.post(
        f"/plan-versions/{version_id}/audit", json={"account_equity": equity}
    )
    assert response.status_code == 200, response.text
    return response.json()


def _submit(client: TestClient, version_id: str) -> None:
    response = client.post(f"/plan-versions/{version_id}/submit")
    assert response.status_code == 200, response.text


def _decide(client: TestClient, version_id: str, **body: object) -> object:
    return client.post(f"/plan-versions/{version_id}/decision", json=body)


def test_create_and_list_plans(api_client: TestClient) -> None:
    plan = _create_plan(api_client)
    assert plan["instrument_code"] == "600000"
    assert plan["status"]["value"] == "draft"
    assert plan["is_active"] is False
    assert len(plan["versions"]) == 1
    facts = plan["versions"][0]["facts"]
    assert facts["setup_type"]["label"] == "C｜上升趋势早中段回踩"
    assert facts["initial_entry_price_low"] == "10.0000"

    listing = api_client.get("/plans").json()
    assert [item["id"] for item in listing] == [plan["id"]]
    detail = api_client.get(f"/plans/{plan['id']}").json()
    assert detail["versions"][0]["facts"]["entry_mode"]["value"] == "price_range"

    missing = api_client.get("/plans/does-not-exist")
    assert missing.status_code == 404


def test_full_lifecycle_to_effective(api_client: TestClient) -> None:
    plan = _create_plan(api_client)
    version_id = plan["versions"][0]["id"]
    _submit(api_client, version_id)
    audit = _audit_version(api_client, version_id)
    assert audit["level"]["value"] == "pass"
    assert audit["summary"].startswith("共 6 条检查结果")

    response = _decide(api_client, version_id, approve=True)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["decision"]["status"] == "not_applicable"
    assert payload["version"]["state"]["value"] == "effective"

    detail = api_client.get(f"/plans/{plan['id']}").json()
    assert detail["status"]["value"] == "active"
    assert detail["is_active"] is True
    assert detail["effective_version_id"] == version_id


def test_audit_persists_findings_and_skipped_rules(api_client: TestClient) -> None:
    plan = _create_plan(api_client)
    version_id = plan["versions"][0]["id"]
    response = api_client.post(f"/plan-versions/{version_id}/audit", json={})
    assert response.status_code == 200, response.text
    audit = response.json()
    rules = {finding["rule"] for finding in audit["details"]["findings"]}
    assert "plan_completeness" not in rules
    assert {"initial_position", "confirmation_position", "t_reserve_position"} <= rules
    assert "target_one_reduce_pct" in rules
    skipped = {item["rule"]: item["reason"] for item in audit["details"]["skipped_rules"]}
    assert "single_trade_risk" in skipped
    assert audit["details"]["account_equity"] is None

    detail = api_client.get(f"/plans/{plan['id']}").json()
    assert detail["versions"][0]["audit_results"][0]["id"] == audit["id"]


def test_hard_fail_blocks_activation(api_client: TestClient) -> None:
    # 30% 总仓位 × 11% 亏损幅度 = 3.3% 单笔风险，超过 3% 硬性上限
    plan = _create_plan(api_client, structure_invalidation_price="8.90")
    version_id = plan["versions"][0]["id"]
    _submit(api_client, version_id)
    audit = _audit_version(api_client, version_id)
    assert audit["level"]["value"] == "hard_fail"

    response = _decide(api_client, version_id, approve=True, user_confirmed=True, override_reason="理由")
    assert response.status_code == 409
    assert "硬性失败" in response.json()["detail"]
    detail = api_client.get(f"/plans/{plan['id']}").json()
    assert detail["status"]["value"] == "draft"


def test_overridable_fail_requires_confirmation_and_records_override(api_client: TestClient) -> None:
    plan = _create_plan(api_client, initial_entry_pct="50")  # outside 35%-45%
    version_id = plan["versions"][0]["id"]
    _submit(api_client, version_id)
    audit = _audit_version(api_client, version_id)
    assert audit["level"]["value"] == "overridable_fail"

    blocked = _decide(api_client, version_id, approve=True)
    assert blocked.status_code == 409
    assert "覆盖理由" in blocked.json()["detail"]

    response = _decide(
        api_client,
        version_id,
        approve=True,
        user_confirmed=True,
        override_reason="趋势结构强于常规，人工决定提高初始仓位",
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["decision"]["status"] == "approved_with_override"
    assert payload["version"]["state"]["value"] == "effective_with_override"

    detail = api_client.get(f"/plans/{plan['id']}").json()
    audits = detail["versions"][0]["audit_results"]
    assert len(audits[0]["overrides"]) == 1
    assert audits[0]["overrides"][0]["reason"] == "趋势结构强于常规，人工决定提高初始仓位"
    assert detail["status"]["value"] == "active"


def test_decision_without_audit_conflicts(api_client: TestClient) -> None:
    plan = _create_plan(api_client)
    version_id = plan["versions"][0]["id"]
    response = _decide(api_client, version_id, approve=True)
    assert response.status_code == 409
    assert "审计结果" in response.json()["detail"]


def test_reject_marks_version_rejected(api_client: TestClient) -> None:
    plan = _create_plan(api_client)
    version_id = plan["versions"][0]["id"]
    _submit(api_client, version_id)
    _audit_version(api_client, version_id)
    response = _decide(api_client, version_id, approve=False)
    assert response.status_code == 200, response.text
    assert response.json()["version"]["state"]["value"] == "rejected"


def test_revision_creates_new_draft_version(api_client: TestClient) -> None:
    plan = _create_plan(api_client)
    version_id = plan["versions"][0]["id"]
    _submit(api_client, version_id)
    _audit_version(api_client, version_id)
    _decide(api_client, version_id, approve=True)

    response = api_client.post(
        f"/plans/{plan['id']}/revisions",
        json={
            "reason": "第一目标上调",
            "changes": {"first_target_price": "12.00"},
        },
    )
    assert response.status_code == 201, response.text
    detail = response.json()
    assert len(detail["versions"]) == 2
    new_version = detail["versions"][-1]
    assert new_version["version_number"] == 2
    assert new_version["state"]["value"] == "draft"
    assert new_version["facts"]["first_target_price"] == "12.0000"
    assert new_version["facts"]["initial_entry_price_low"] == "10.0000"


def test_note_update_and_close(api_client: TestClient) -> None:
    plan = _create_plan(api_client)
    note = api_client.patch(f"/plans/{plan['id']}/note", json={"user_note": "等待回踩确认"})
    assert note.status_code == 200
    assert note.json()["user_note"] == "等待回踩确认"

    closed = api_client.post(f"/plans/{plan['id']}/close")
    assert closed.status_code == 200
    assert closed.json()["status"]["value"] == "closed"
    assert closed.json()["is_active"] is False


def test_create_plan_requires_equity_for_amount_conversion(api_client: TestClient) -> None:
    payload = {
        "instrument_code": "600000",
        "instrument_name": "浦发银行",
        "version": {**PASSING_VERSION},
    }
    payload["version"].pop("initial_entry_pct")
    payload["version"]["planned_total_position_pct"] = "40"
    response = api_client.post("/plans", json=payload)
    assert response.status_code == 409
    assert "账户总权益" in response.json()["detail"]
