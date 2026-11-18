"""Account/holdings CSV import API tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

ACCOUNT_CSV = "equity,available_cash,as_of\n1000000,500000,2026-11-18T10:00:00+08:00"
HOLDINGS_CSV = "symbol,quantity,cost,as_of\n600000,10000,10.20,2026-11-18T10:00:00+08:00"


def _import(client: TestClient, kind: str, data: str) -> object:
    return client.post("/account/imports/csv", json={"kind": kind, "data": data})


def test_import_account_csv(api_client: TestClient) -> None:
    response = _import(api_client, "account", ACCOUNT_CSV)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["duplicate"] is False
    snapshot = payload["snapshot"]
    assert snapshot["total_equity"] == "1000000.0000"
    assert snapshot["source"] == "csv"


def test_import_account_csv_is_idempotent(api_client: TestClient) -> None:
    first = _import(api_client, "account", ACCOUNT_CSV)
    assert first.status_code == 200
    second = _import(api_client, "account", ACCOUNT_CSV)
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    listing = api_client.get("/account/snapshots").json()
    assert len(listing) == 1


def test_import_holdings_csv_creates_equity_unknown_snapshot(api_client: TestClient) -> None:
    response = _import(api_client, "holdings", HOLDINGS_CSV)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["imported"] == 1
    snapshot = payload["snapshots"][0]
    assert snapshot["total_equity"] is None
    assert snapshot["positions"][0]["instrument_code"] == "600000"
    assert snapshot["positions"][0]["total_quantity"] == "10000.0000"
    assert snapshot["positions"][0]["broker_cost_price"] == "10.2000"


def test_import_holdings_csv_is_idempotent(api_client: TestClient) -> None:
    _import(api_client, "holdings", HOLDINGS_CSV)
    second = _import(api_client, "holdings", HOLDINGS_CSV)
    assert second.status_code == 200
    assert second.json()["duplicates"] == 1
    listing = api_client.get("/account/snapshots").json()
    assert len(listing) == 1


def test_import_holdings_reuses_known_instrument_name(api_client: TestClient) -> None:
    named = {
        "captured_at": "2026-11-17T09:00:00+08:00",
        "total_equity": "1000000",
        "available_cash": "500000",
        "positions": [
            {"instrument_code": "600000", "instrument_name": "浦发银行", "total_quantity": "1"}
        ],
    }
    created = api_client.post("/account/snapshots", json=named)
    assert created.status_code == 201

    response = _import(api_client, "holdings", HOLDINGS_CSV)
    assert response.status_code == 200
    snapshot = response.json()["snapshots"][0]
    assert snapshot["positions"][0]["instrument_name"] == "浦发银行"


def test_import_rejects_malformed_csv(api_client: TestClient) -> None:
    response = _import(api_client, "account", "equity,available_cash\n1,2")
    assert response.status_code == 400
    assert "字段" in response.json()["detail"]

    empty = _import(api_client, "account", "equity,available_cash,as_of\n")
    assert empty.status_code == 400


def test_import_rejects_duplicate_instrument_in_batch(api_client: TestClient) -> None:
    csv_text = (
        "symbol,quantity,cost,as_of\n"
        "600000,100,10.00,2026-11-18T10:00:00+08:00\n"
        "600000,200,10.10,2026-11-18T10:00:00+08:00"
    )
    response = _import(api_client, "holdings", csv_text)
    assert response.status_code == 409
    assert "重复证券代码" in response.json()["detail"]


def test_import_rejects_unknown_kind(api_client: TestClient) -> None:
    response = _import(api_client, "fills", "a,b\n1,2")
    assert response.status_code == 409
    assert "未知 CSV 类型" in response.json()["detail"]
