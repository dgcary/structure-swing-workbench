"""LLM plan drafting API tests with injected fake completers."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.api.deps import get_llm_complete

VALID_LLM_JSON = {
    "instrument_code": "600000",
    "instrument_name": "浦发银行",
    "setup_type": "c",
    "structure_stage": "early",
    "entry_mode": "price_range",
    "initial_entry_price_low": "10.00",
    "initial_entry_price_high": "10.50",
    "structure_invalidation_price": "9.60",
    "structure_invalidation_condition": "收盘跌破9.60",
    "planned_total_position_pct": "30",
    "initial_entry_pct": "40",
    "confirmation_add_pct": "30",
    "t_reserve_pct": "30",
    "first_target_price": "11.50",
    "first_target_type": "prior_high",
    "first_target_reduce_pct": "50",
    # 主观确认字段即使 LLM 返回也必须被丢弃
    "reversal_confirmed": True,
    "structure_invalidated": True,
}


def _configure(client: TestClient, raw: str) -> None:
    def fake_complete(system: str, user: str) -> str:
        return raw

    client.app.dependency_overrides[get_llm_complete] = lambda: fake_complete


def _release(client: TestClient) -> None:
    client.app.dependency_overrides.pop(get_llm_complete, None)


def _parse(client: TestClient, text: str) -> object:
    return client.post("/plans/parse", json={"text": text})


def test_parse_valid_text_returns_safe_draft(api_client: TestClient) -> None:
    _configure(api_client, json.dumps(VALID_LLM_JSON, ensure_ascii=False))
    try:
        response = _parse(api_client, "浦发银行 C类回踩，10块到10块5建仓，跌破9块6止损，三成仓位")
    finally:
        _release(api_client)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["draft"]["instrument_code"] == "600000"
    assert payload["draft"]["instrument_name"] == "浦发银行"
    data = payload["draft"]["version_data"]
    assert data["setup_type"] == "c"
    assert data["entry_mode"] == "price_range"
    assert data["initial_entry_price_low"] == "10.0000"
    assert data["structure_invalidation_price"] == "9.6000"
    assert data["planned_total_position_pct"] == "30.0000"
    # 架构边界：主观确认字段永不来自 LLM
    assert "reversal_confirmed" not in data
    assert "structure_invalidated" not in data
    assert payload["warnings"] == []


def test_parse_accepts_markdown_fenced_json(api_client: TestClient) -> None:
    raw = "```json\n" + json.dumps(VALID_LLM_JSON, ensure_ascii=False) + "\n```"
    _configure(api_client, raw)
    try:
        response = _parse(api_client, "浦发银行区间建仓")
    finally:
        _release(api_client)
    assert response.status_code == 200, response.text
    assert response.json()["draft"]["instrument_code"] == "600000"


def test_parse_drops_invalid_enum_and_reports_warning(api_client: TestClient) -> None:
    broken = dict(VALID_LLM_JSON)
    broken["setup_type"] = "x"
    broken["initial_entry_price_low"] = "abc"
    _configure(api_client, json.dumps(broken, ensure_ascii=False))
    try:
        response = _parse(api_client, "描述")
    finally:
        _release(api_client)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "setup_type" not in payload["draft"]["version_data"]
    assert "initial_entry_price_low" not in payload["draft"]["version_data"]
    warnings = " ".join(payload["warnings"])
    assert "Setup" in warnings
    assert "计划买入下沿" in warnings


def test_parse_rejects_entry_high_below_low(api_client: TestClient) -> None:
    broken = dict(VALID_LLM_JSON)
    broken["initial_entry_price_high"] = "9.00"
    _configure(api_client, json.dumps(broken, ensure_ascii=False))
    try:
        response = _parse(api_client, "描述")
    finally:
        _release(api_client)
    assert response.status_code == 200
    payload = response.json()
    assert "initial_entry_price_high" not in payload["draft"]["version_data"]
    assert any("上沿" in warning for warning in payload["warnings"])


def test_parse_rejects_invalid_json(api_client: TestClient) -> None:
    _configure(api_client, "这不是 JSON")
    try:
        response = _parse(api_client, "描述")
    finally:
        _release(api_client)
    assert response.status_code == 502
    assert "JSON" in response.json()["detail"]


def test_parse_unconfigured_returns_503(api_client: TestClient) -> None:
    # 未覆盖依赖时，默认配置没有 LLM → 503
    response = _parse(api_client, "描述")
    assert response.status_code == 503
    assert "LLM" in response.json()["detail"]
