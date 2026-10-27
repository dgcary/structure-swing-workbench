"""M8 uploaded account facts must never become a live or persistent account."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

ACCOUNT_CSV = (
    "equity,available_cash,as_of\n"
    "200000,65000,2026-10-16T09:30:00+08:00\n"
)


def test_uploaded_account_snapshot_is_request_scoped() -> None:
    preview = client.post(
        "/workbench/account-snapshot-preview", json={"account": ACCOUNT_CSV}
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["persisted"] is False
    assert body["realtime"] is False
    assert body["full_account_verified"] is False
    assert body["trade_execution_enabled"] is False
    metrics = {item["key"]: item for item in body["metrics"]}
    assert metrics["equity"]["value"] == "200000"
    assert metrics["available_cash"]["value"] == "65000"
    assert metrics["account_risk"]["value"] is None

    live = client.get("/workbench/overview")
    assert live.status_code == 200
    assert all(item["value"] is None for item in live.json()["metrics"])


def test_empty_or_invalid_account_upload_fails_closed() -> None:
    for data in ({}, {"account": "  "}, {"account": "bad,header\n1,2\n"}):
        response = client.post("/workbench/account-snapshot-preview", json=data)
        assert response.status_code == 422


@pytest.mark.parametrize(("kind", "row"), [
    ("account", "equity,available_cash,as_of\\n200000,65000,{at}\\n"),
    ("holdings", "symbol,quantity,cost,as_of\\n600000,100,10,{at}\\n"),
    ("fills", "fill_id,symbol,side,quantity,price,executed_at\\n"
              "future-fill,600000,BUY,100,10,{at}\\n"),
])
def test_future_dated_uploaded_facts_fail_closed(kind: str, row: str) -> None:
    # All three user-supplied CSV sources must be observed, not future facts.
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    response = client.post(
        "/workbench/account-snapshot-preview", json={kind: row.format(at=future)}
    )
    assert response.status_code == 422
    assert "未来时间" in response.json()["detail"]


def test_small_upload_clock_skew_remains_display_only() -> None:
    # Allow a small timestamp skew, never interpret it as broker connectivity.
    near_future = (datetime.now(UTC) + timedelta(minutes=1)).isoformat()
    response = client.post(
        "/workbench/account-snapshot-preview",
        json={"account": (
            "equity,available_cash,as_of\\n"
            f"200000,65000,{near_future}\\n"
        )},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["persisted"] is False
    assert payload["realtime"] is False
    assert payload["trade_execution_enabled"] is False
