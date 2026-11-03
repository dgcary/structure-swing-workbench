"""Manual account records are opt-in, authenticated, and transport protected."""

from datetime import UTC, datetime

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


def test_manual_journal_rejects_weak_token_and_missing_or_wrong_credential(monkeypatch):
    _settings(monkeypatch, token="short")
    client = TestClient(api.app, base_url="https://example.test")
    assert client.get("/workbench/manual-journal").status_code == 503
    _settings(monkeypatch)
    for header in ({}, {"Authorization": "Bearer wrong"}):
        response = client.get("/workbench/manual-journal", headers=header)
        assert response.status_code == 401
        assert "1000" not in response.text


def test_manual_journal_rejects_lan_http_even_with_token(monkeypatch):
    _settings(monkeypatch)
    headers = {"Authorization": "Bearer " + "x" * 40,
               "X-Forwarded-Proto": "https"}
    client = TestClient(api.app, base_url="http://192.168.1.10")
    assert client.get("/workbench/manual-journal", headers=headers).status_code == 403
    assert client.post("/workbench/manual-journal", json=_payload(),
                       headers=headers).status_code == 403


def test_manual_journal_roundtrip_and_conflict(monkeypatch, tmp_path):
    _settings(monkeypatch)
    db_file = tmp_path / "journal.sqlite"
    engine = create_engine(f"sqlite+pysqlite:///{db_file}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(api, "build_engine", lambda: engine)
    monkeypatch.setattr(engine, "dispose", lambda: None)
    headers = {"Authorization": "Bearer " + "x" * 40}
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
