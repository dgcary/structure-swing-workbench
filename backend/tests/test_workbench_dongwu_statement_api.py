"""Only safe aggregate statement evidence may leave the local PDF parser."""

from datetime import date

from fastapi import Request
from fastapi.testclient import TestClient

import app.main as api
from app.core.config import Settings
from app.workbench.dongwu_statement import StatementCheck


def _enable(monkeypatch, *, host: str = "127.0.0.1") -> None:
    monkeypatch.setattr(api, "settings", Settings(
        app_host=host, workbench_statement_check_enabled=True,
    ))
    monkeypatch.setattr(api, "_local_statement_transport", lambda _: True)


def test_pdf_upload_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr(api, "settings", Settings(workbench_statement_check_enabled=False))
    response = TestClient(api.app).post(
        "/workbench/dongwu-statement-check", content=b"%PDF",
        headers={"Content-Type": "application/pdf"},
    )
    assert response.status_code == 404


def _request(host: str, peer: str, origin: str | None) -> Request:
    headers = [(b"host", host.encode("ascii"))]
    if origin is not None:
        headers.append((b"origin", origin.encode("ascii")))
    return Request({
        "type": "http", "scheme": "http", "method": "POST",
        "path": "/", "query_string": b"", "headers": headers,
        "server": (host, 8000), "client": (peer, 12345),
    })


def test_pdf_upload_transport_requires_loopback_peer_host_and_origin():
    trusted = api._local_statement_transport
    assert trusted(_request("localhost", "127.0.0.1", "http://localhost:5173"))
    assert trusted(_request("127.0.0.1", "::1", "http://127.0.0.1:5173"))
    assert not trusted(_request("localhost", "203.0.113.9", "http://localhost:5173"))
    assert not trusted(_request("workbench.example", "127.0.0.1", "http://localhost:5173"))
    assert not trusted(_request("localhost", "127.0.0.1", "https://workbench.example"))
    assert not trusted(_request("localhost", "127.0.0.1", None))


def test_local_frontend_origins_can_preflight_direct_pdf_upload():
    client = TestClient(api.app)
    for origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
        response = client.options(
            "/workbench/dongwu-statement-check",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin


def test_pdf_upload_requires_loopback_backend_even_when_enabled(monkeypatch):
    _enable(monkeypatch, host="0.0.0.0")
    response = TestClient(api.app).post(
        "/workbench/dongwu-statement-check", content=b"%PDF",
        headers={"Content-Type": "application/pdf"},
    )
    assert response.status_code == 403


def test_pdf_upload_rejects_wrong_media_type_and_stream_over_cap(monkeypatch):
    _enable(monkeypatch)
    client = TestClient(api.app)
    assert client.post(
        "/workbench/dongwu-statement-check", content=b"%PDF",
        headers={"Content-Type": "application/zip"},
    ).status_code == 415
    monkeypatch.setattr(api, "MAX_STATEMENT_UPLOAD_BYTES", 8)
    assert client.post(
        "/workbench/dongwu-statement-check", content=b"%PDF" + b"x" * 9,
        headers={"Content-Type": "application/pdf"},
    ).status_code == 413


def test_pdf_upload_returns_aggregate_only_and_does_not_change_overview(monkeypatch):
    _enable(monkeypatch)
    received = []

    def check(data: bytes) -> StatementCheck:
        received.append(data)
        return StatementCheck(
            status="matched_unverified", period_start=date(2026, 8, 5),
            period_end=date(2026, 11, 2), summary_row_count=48,
            detail_row_count=52, matched_group_count=48,
            missing_summary_group_count=0, extra_summary_group_count=0,
            mismatched_group_count=0, repaired_summary_rows=3,
            footer_totals_checked=True,
        )

    monkeypatch.setattr(api, "check_dongwu_statement_pdf", check)
    client = TestClient(api.app)
    response = client.post(
        "/workbench/dongwu-statement-check", content=b"%PDF synthetic private bytes",
        headers={"Content-Type": "application/pdf"},
    )
    assert response.status_code == 200
    body = response.json()
    assert received == [b"%PDF synthetic private bytes"]
    assert body["schema_version"] == "m8.dongwu_statement_check.v1"
    assert body["mode"] == "local_pdf_preview"
    assert body["status"] == "matched_unverified"
    assert body["summary_row_count"] == 48
    assert body["detail_row_count"] == 52
    assert body["footer_totals_checked"] is True
    assert body["broker_reconciled"] is False
    assert body["full_account_verified"] is False
    assert body["trade_execution_enabled"] is False
    assert b"private".decode() not in str(body)
    assert all(item["value"] is None for item in client.get("/workbench/overview").json()["metrics"])


def test_pdf_upload_has_explicit_output_allowlist_when_parser_adds_private_field(monkeypatch):
    _enable(monkeypatch)

    class FutureCheck:
        def __init__(self):
            self.status = "matched_unverified"
            self.period_start = date(2026, 8, 5)
            self.period_end = date(2026, 11, 2)
            self.summary_row_count = 1
            self.detail_row_count = 1
            self.matched_group_count = 1
            self.missing_summary_group_count = 0
            self.extra_summary_group_count = 0
            self.mismatched_group_count = 0
            self.repaired_summary_rows = 0
            self.footer_totals_checked = True
            self.footer_totals_mismatched_count = 0
            self.broker_reconciled = False
            self.full_account_verified = False
            self.trade_execution_enabled = False
            self.execution_ids_available = False
            self.execution_times_available = False
            self.account_id = "private account"

    monkeypatch.setattr(api, "check_dongwu_statement_pdf", lambda _: FutureCheck())
    response = TestClient(api.app).post(
        "/workbench/dongwu-statement-check", content=b"%PDF",
        headers={"Content-Type": "application/pdf"},
    )
    assert response.status_code == 200
    assert "private account" not in str(response.json())
    assert "account_id" not in response.json()


def test_pdf_upload_invalid_document_returns_generic_error(monkeypatch):
    _enable(monkeypatch)

    def fail(_: bytes):
        raise ValueError("private text")

    monkeypatch.setattr(api, "check_dongwu_statement_pdf", fail)
    response = TestClient(api.app).post(
        "/workbench/dongwu-statement-check", content=b"%PDF",
        headers={"Content-Type": "application/pdf"},
    )
    assert response.status_code == 422
    assert "private" not in str(response.json())
