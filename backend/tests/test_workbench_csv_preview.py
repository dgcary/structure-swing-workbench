from fastapi.testclient import TestClient

from app.main import app


def test_csv_preview_contract():
    response = TestClient(app).post(
        "/workbench/csv-preview",
        json={
            "kind": "account",
            "data": "equity,available_cash,as_of\n200000,65000,2026-10-16T09:30:00+08:00\n",
        },
    )
    assert response.status_code == 200
    assert response.json()["persisted"] is False
    assert response.json()["trade_execution_enabled"] is False
