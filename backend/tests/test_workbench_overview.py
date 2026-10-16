from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from app.account import AccountLedger, correct_account
from app.main import app
from app.workbench.overview import build_overview


def test_unconnected_overview_is_not_zero_or_pass() -> None:
    overview = build_overview()
    assert overview["mode"] == "read_only"
    assert overview["trade_execution_enabled"] is False
    assert overview["holdings"] is None
    assert overview["audit_results"] is None
    assert len(overview["metrics"]) == 9
    assert all(metric["value"] is None for metric in overview["metrics"])


def test_known_facts_retain_provenance() -> None:
    ledger = AccountLedger()
    at = datetime(2026, 10, 16, 9, 30, tzinfo=UTC)
    correct_account(ledger, equity=Decimal("200000"), cash=Decimal("65000"),
                    at=at, source_id="manual-001")
    metrics = {item["key"]: item for item in build_overview(ledger)["metrics"]}
    assert metrics["equity"]["value"] == "200000"
    assert metrics["equity"]["source"] == "manual/manual-001"
    assert metrics["equity"]["as_of"] == at.isoformat()
    assert metrics["available_cash"]["value"] == "65000"
    assert metrics["account_risk"]["value"] is None


def test_api_never_uses_fixture_as_live_account() -> None:
    response = TestClient(app).get("/workbench/overview")
    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "m8.overview.v1"
    assert all(item["status"] == "unavailable" for item in payload["metrics"])
