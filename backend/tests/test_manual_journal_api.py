"""Manual account records are opt-in, authenticated, and transport protected."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app import main as api
from app.core.config import Settings
from app.db import Base


def _settings(monkeypatch, *, enabled=True, token="x" * 40):
    monkeypatch.setattr(api, "settings", Settings(
        workbench_manual_journal_enabled=enabled,
        workbench_manual_journal_token=token,
    ))


def _payload(expected_revision=0):
    now = datetime.now(UTC).isoformat()
    return {
        "expected_revision": expected_revision,
        "observed_at": now,
        "available_cash": "1000",
        "lots": [],
    }


def test_manual_journal_disabled_by_default(monkeypatch):
    _settings(monkeypatch, enabled=False)
    client = TestClient(api.app, base_url="https://example.test")
    assert client.get("/workbench/manual-journal").status_code == 404
    assert client.post("/workbench/manual-journal", json=_payload()).status_code == 404
    assert client.post("/workbench/manual-journal/operation", json={}).status_code == 404


def test_manual_journal_rejects_weak_token_and_missing_or_wrong_credential(monkeypatch):
    _settings(monkeypatch, token="short")
    client = TestClient(api.app, base_url="https://example.test")
    assert client.get("/workbench/manual-journal").status_code == 503
    _settings(monkeypatch)
    for header in ({}, {"X-Workbench-Journal-Token": "wrong"}):
        response = client.get("/workbench/manual-journal", headers=header)
        assert response.status_code == 401
        assert "1000" not in response.text


def test_manual_journal_rejects_lan_http_even_with_token(monkeypatch):
    _settings(monkeypatch)
    headers = {"X-Workbench-Journal-Token": "x" * 40,
               "X-Forwarded-Proto": "https"}
    client = TestClient(api.app, base_url="http://192.168.1.10")
    assert client.get("/workbench/manual-journal", headers=headers).status_code == 403
    assert client.post("/workbench/manual-journal", json=_payload(),
                       headers=headers).status_code == 403
    assert client.post("/workbench/manual-journal/operation", json={},
                       headers=headers).status_code == 403


def test_manual_journal_roundtrip_and_conflict(monkeypatch, tmp_path):
    _settings(monkeypatch)
    db_file = tmp_path / "journal.sqlite"
    engine = create_engine(f"sqlite+pysqlite:///{db_file}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(api, "build_engine", lambda: engine)
    monkeypatch.setattr(engine, "dispose", lambda: None)
    headers = {"X-Workbench-Journal-Token": "x" * 40}
    client = TestClient(api.app, base_url="https://example.test")
    empty = client.get("/workbench/manual-journal", headers=headers)
    assert empty.status_code == 200
    assert empty.json()["latest_revision"] == 0
    saved = client.post("/workbench/manual-journal", json=_payload(), headers=headers)
    assert saved.status_code == 201
    assert saved.json()["source"] == "user_manual"
    assert saved.json()["broker_reconciled"] is False
    assert saved.json()["trade_execution_enabled"] is False
    current = client.get("/workbench/manual-journal", headers=headers)
    assert current.json()["latest"]["id"] == saved.json()["id"]
    conflict = client.post("/workbench/manual-journal", json=_payload(), headers=headers)
    assert conflict.status_code == 409
    assert client.get("/workbench/manual-journal", headers=headers).json()["total_revisions"] == 1
    engine.dispose()


def test_whole_site_login_and_journal_token_can_coexist(monkeypatch, tmp_path):
    _settings(monkeypatch)
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'journal_auth.sqlite'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(api, "build_engine", lambda: engine)
    monkeypatch.setattr(engine, "dispose", lambda: None)
    client = TestClient(api.app, base_url="https://example.test")
    headers = {
        "Authorization": "Basic whole-site-credential",
        "X-Workbench-Journal-Token": "x" * 40,
    }
    response = client.post("/workbench/manual-journal", json=_payload(), headers=headers)
    assert response.status_code == 201
    assert client.get("/workbench/manual-journal", headers=headers).status_code == 200
    assert client.get("/workbench/manual-journal", headers={
        "Authorization": "Bearer " + "x" * 40,
    }).status_code == 401


def test_snapshot_api_cannot_claim_a_trade_without_applying_it(monkeypatch, tmp_path):
    _settings(monkeypatch)
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'journal_snapshot_trade.sqlite'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(api, "build_engine", lambda: engine)
    monkeypatch.setattr(engine, "dispose", lambda: None)
    client = TestClient(api.app, base_url="https://example.test")
    headers = {"X-Workbench-Journal-Token": "x" * 40}
    payload = _payload()
    payload["operation"] = {
        "side": "BUY", "symbol": "600000.SH", "quantity": "100", "price": "10",
        "executed_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
    }
    assert client.post("/workbench/manual-journal", json=payload,
                       headers=headers).status_code == 422
    assert client.get("/workbench/manual-journal", headers=headers).json()[
        "latest_revision"] == 0


def test_operation_api_updates_latest_lots_and_rejects_stale_or_invalid_sale(
    monkeypatch, tmp_path,
):
    _settings(monkeypatch)
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'journal_operation.sqlite'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(api, "build_engine", lambda: engine)
    monkeypatch.setattr(engine, "dispose", lambda: None)
    client = TestClient(api.app, base_url="https://example.test")
    headers = {"X-Workbench-Journal-Token": "x" * 40}
    now = datetime.now(UTC).replace(microsecond=0)
    baseline = _payload()
    baseline["observed_at"] = (now - timedelta(hours=2)).isoformat()
    baseline["lots"] = [{"symbol": "600000.SH", "quantity": "100",
                         "paid_amount": "980", "bought_at": None}]
    assert client.post("/workbench/manual-journal", json=baseline,
                       headers=headers).status_code == 201
    action = {
        "expected_revision": 1, "observed_at": now.isoformat(),
        "sell_lot_index": 0,
        "operation": {"side": "SELL", "symbol": "600000.SH", "quantity": "40",
                      "price": "10", "executed_at":
                      (now - timedelta(minutes=1)).isoformat()},
    }
    saved = client.post("/workbench/manual-journal/operation", json=action,
                        headers=headers)
    assert saved.status_code == 201
    assert saved.json()["lots"][0]["quantity"] == "60"
    assert saved.json()["lots"][0]["paid_amount"] is None
    assert client.get("/workbench/manual-journal", headers=headers).json()[
        "latest_revision"] == 2
    assert client.post("/workbench/manual-journal/operation", json=action,
                       headers=headers).status_code == 409
    action["expected_revision"] = 2
    action["sell_lot_index"] = 99
    action["operation"]["executed_at"] = (now + timedelta(seconds=1)).isoformat()
    action["observed_at"] = (now + timedelta(seconds=2)).isoformat()
    assert client.post("/workbench/manual-journal/operation", json=action,
                       headers=headers).status_code == 422


def test_operation_api_applies_one_sale_across_multiple_lots(monkeypatch, tmp_path):
    _settings(monkeypatch)
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'journal_multilot.sqlite'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(api, "build_engine", lambda: engine)
    monkeypatch.setattr(engine, "dispose", lambda: None)
    client = TestClient(api.app, base_url="https://example.test")
    headers = {"X-Workbench-Journal-Token": "x" * 40}
    now = datetime.now(UTC).replace(microsecond=0)
    baseline = _payload()
    baseline["observed_at"] = (now - timedelta(hours=2)).isoformat()
    baseline["lots"] = [
        {"symbol": "600000.SH", "quantity": "50"},
        {"symbol": "600000.SH", "quantity": "40"},
    ]
    assert client.post("/workbench/manual-journal", json=baseline,
                       headers=headers).status_code == 201
    action = {
        "expected_revision": 1, "observed_at": now.isoformat(),
        "sell_allocations": [{"lot_index": 0, "quantity": "30"},
                             {"lot_index": 1, "quantity": "40"}],
        "operation": {"side": "SELL", "symbol": "600000.SH", "quantity": "70",
                      "price": "10", "executed_at": (now - timedelta(minutes=1)).isoformat()},
    }
    response = client.post("/workbench/manual-journal/operation", json=action,
                           headers=headers)
    assert response.status_code == 201
    assert [lot["quantity"] for lot in response.json()["lots"]] == ["20"]
    assert client.get("/workbench/manual-journal", headers=headers).json()[
        "latest_revision"] == 2
