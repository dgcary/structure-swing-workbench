"""M8 uploaded account facts must never become a live or persistent account."""

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
