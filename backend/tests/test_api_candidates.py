"""Candidate screening API tests (display only, no trade signals)."""

from __future__ import annotations

from fastapi.testclient import TestClient

EVIDENCE = {
    "source": "交易所公告",
    "reference": "https://example.com/announcement",
    "observed_at": "2026-01-05T09:30:00+08:00",
}


def _candidate(**overrides: object) -> dict:
    item = {
        "symbol": "600000",
        "name": "浦发银行",
        "board": {"value": "MAIN", "evidence": EVIDENCE},
        "liquidity": {"value": "GOOD", "evidence": EVIDENCE},
        "size": {"value": "MID_LARGE", "evidence": EVIDENCE},
        "listing_age": {"value": "ESTABLISHED", "evidence": EVIDENCE},
        "risks": [
            {"code": code, "state": "ABSENT", "evidence": EVIDENCE}
            for code in (
                "ST",
                "DELISTING",
                "REGULATORY_INVESTIGATION",
                "FINANCIAL_FRAUD",
                "QUALIFIED_AUDIT",
                "SEVERE_DEBT",
                "GOING_CONCERN",
            )
        ],
    }
    item.update(overrides)
    return item


def test_screen_fully_checked_candidate(api_client: TestClient) -> None:
    response = api_client.post("/candidates/screen", json=_candidate())
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "CANDIDATE"
    assert payload["missing_risk_checks"] == []
    assert any("不生成买卖信号" in message for message in payload["messages"])


def test_screen_with_missing_red_line_checks_stays_review(api_client: TestClient) -> None:
    response = api_client.post("/candidates/screen", json=_candidate(risks=[]))
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "REVIEW"
    assert len(payload["missing_risk_checks"]) == 7


def test_screen_with_present_risk_is_excluded(api_client: TestClient) -> None:
    item = _candidate()
    item["risks"][0]["state"] = "PRESENT"
    response = api_client.post("/candidates/screen", json=item)
    assert response.status_code == 200
    assert response.json()["status"] == "EXCLUDED"


def test_screen_rejects_invalid_review_lane(api_client: TestClient) -> None:
    response = api_client.post("/candidates/screen", json=_candidate(review_lane="X"))
    assert response.status_code == 400
    assert "复核通道" in response.json()["detail"]


def test_screen_batch_orders_lanes_within_status(api_client: TestClient) -> None:
    lane_c = _candidate(symbol="600000", review_lane="C", review_lane_evidence=EVIDENCE)
    lane_b = _candidate(symbol="000001", review_lane="B", review_lane_evidence=EVIDENCE)
    response = api_client.post("/candidates/screen-batch", json=[lane_b, lane_c])
    assert response.status_code == 200, response.text
    symbols = [item["symbol"] for item in response.json()]
    assert symbols == ["600000", "000001"]
