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
    ("account", "equity,available_cash,as_of\n200000,65000,{at}\n"),
    ("holdings", "symbol,quantity,cost,as_of\n600000,100,10,{at}\n"),
    ("fills", ("fill_id,symbol,side,quantity,price,executed_at\n"
               "future-fill,600000,BUY,100,10,{at}\n")),
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
            "equity,available_cash,as_of\n"
            f"200000,65000,{near_future}\n"
        )},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["persisted"] is False
    assert payload["realtime"] is False
    assert payload["trade_execution_enabled"] is False


FILL_CSV = (
    "fill_id,symbol,side,quantity,price,executed_at\n"
    "A01,600000,BUY,100,10,2026-10-16T10:00:00+08:00\n"
    "A02,600000,SELL,100,11,2026-10-16T11:00:00+08:00\n"
)


def _daily_claim(**overrides):
    claim = {
        "market_date": "2026-10-16",
        "exported_at": "2026-10-16T16:00:00+08:00",
        "complete_through": "2026-10-16T15:30:00+08:00",
        "export_reference": "脱敏券商导出-001",
        "expected_fill_ids": ["A01", "A02"],
        "declared_full_day": True,
    }
    claim.update(overrides)
    return claim


def test_daily_fill_manifest_matches_ids_but_never_certifies_broker_or_t_count():
    response = client.post("/workbench/account-snapshot-preview", json={
        "fills": FILL_CSV, "daily_fill_claim": _daily_claim(),
    })
    assert response.status_code == 200, response.text
    body = response.json()
    coverage = body["daily_fill_coverage"]
    assert coverage["status"] == "matched_unverified"
    assert coverage["recorded_fill_count"] == 2
    assert coverage["declared_fill_count"] == 2
    assert coverage["missing_fill_count"] == 0
    assert coverage["unexpected_fill_count"] == 0
    assert coverage["broker_reconciled"] is False
    assert coverage["trade_execution_enabled"] is False
    assert "没有独立券商来源认证" in coverage["warning"]
    assert body["full_account_verified"] is False
    assert body["trade_execution_enabled"] is False
    metrics = {item["key"]: item for item in body["metrics"]}
    assert metrics["t_cycles_today"]["status"] == "unavailable"
    assert metrics["open_t_cycles"]["status"] == "unavailable"


@pytest.mark.parametrize(("expected", "missing", "unexpected"), [
    (["A01", "missing"], 1, 1),
    (["A01"], 0, 1),
    (["A01", "A02", "A03"], 1, 0),
])
def test_daily_fill_manifest_detects_missing_and_unexpected_ids(
    expected, missing, unexpected,
):
    response = client.post("/workbench/account-snapshot-preview", json={
        "fills": FILL_CSV,
        "daily_fill_claim": _daily_claim(expected_fill_ids=expected),
    })
    assert response.status_code == 200, response.text
    coverage = response.json()["daily_fill_coverage"]
    assert coverage["status"] == "mismatch"
    assert coverage["missing_fill_count"] == missing
    assert coverage["unexpected_fill_count"] == unexpected
    assert coverage["broker_reconciled"] is False


@pytest.mark.parametrize("late_at", [
    "2026-10-16T15:45:00+08:00",
    "2026-10-16T07:45:00+00:00",
])
def test_daily_fill_manifest_rejects_fills_after_claimed_watermark(late_at):
    # Identical ID sets do not prove that the declared time range covers all rows.
    late_csv = FILL_CSV.replace("2026-10-16T11:00:00+08:00", late_at)
    response = client.post("/workbench/account-snapshot-preview", json={
        "fills": late_csv, "daily_fill_claim": _daily_claim(),
    })
    assert response.status_code == 200, response.text
    coverage = response.json()["daily_fill_coverage"]
    assert coverage["status"] == "mismatch"
    assert coverage["outside_watermark_fill_count"] == 1
    assert coverage["missing_fill_count"] == 0
    assert coverage["unexpected_fill_count"] == 0
    assert coverage["broker_reconciled"] is False
    assert response.json()["trade_execution_enabled"] is False


def test_daily_fill_manifest_accepts_fill_at_exact_watermark_only_as_unverified():
    boundary_csv = FILL_CSV.replace(
        "2026-10-16T11:00:00+08:00", "2026-10-16T07:30:00+00:00"
    )
    response = client.post("/workbench/account-snapshot-preview", json={
        "fills": boundary_csv, "daily_fill_claim": _daily_claim(),
    })
    assert response.status_code == 200, response.text
    coverage = response.json()["daily_fill_coverage"]
    assert coverage["status"] == "matched_unverified"
    assert coverage["outside_watermark_fill_count"] == 0
    assert coverage["broker_reconciled"] is False
    assert response.json()["full_account_verified"] is False


def test_daily_fill_manifest_duplicate_csv_rows_are_not_silent_completeness():
    duplicated = FILL_CSV + FILL_CSV.splitlines(keepends=True)[1]
    response = client.post("/workbench/account-snapshot-preview", json={
        "fills": duplicated, "daily_fill_claim": _daily_claim(),
    })
    assert response.status_code == 200, response.text
    coverage = response.json()["daily_fill_coverage"]
    assert coverage["status"] == "mismatch"
    assert coverage["duplicate_csv_rows"] == 1
    assert coverage["broker_reconciled"] is False


def test_daily_fill_manifest_before_close_is_insufficient_even_if_ids_match():
    response = client.post("/workbench/account-snapshot-preview", json={
        "fills": FILL_CSV,
        "daily_fill_claim": _daily_claim(
            exported_at="2026-10-16T14:00:00+08:00",
            complete_through="2026-10-16T13:30:00+08:00",
        ),
    })
    assert response.status_code == 200, response.text
    assert response.json()["daily_fill_coverage"]["status"] == "insufficient"


@pytest.mark.parametrize("claim", [
    _daily_claim(expected_fill_ids=["A01", "A01"]),
    _daily_claim(exported_at="2026-10-16T16:00:00",
                 complete_through="2026-10-16T15:30:00+08:00"),
    _daily_claim(exported_at="2026-10-16T14:00:00+08:00"),
    _daily_claim(export_reference="  "),
    _daily_claim(expected_fill_ids=[" A01", "A02"]),
])
def test_daily_fill_manifest_rejects_ambiguous_claims(claim):
    response = client.post("/workbench/account-snapshot-preview", json={
        "fills": FILL_CSV, "daily_fill_claim": claim,
    })
    assert response.status_code == 422


def test_daily_fill_manifest_requires_csv_and_rejects_future_watermark():
    no_fills = client.post("/workbench/account-snapshot-preview", json={
        "account": ACCOUNT_CSV, "daily_fill_claim": _daily_claim(),
    })
    assert no_fills.status_code == 422
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    response = client.post("/workbench/account-snapshot-preview", json={
        "fills": FILL_CSV,
        "daily_fill_claim": _daily_claim(exported_at=future, complete_through=future),
    })
    assert response.status_code == 422
    assert "未来" in response.json()["detail"]


def test_daily_fill_manifest_not_provided_remains_explicitly_unavailable():
    response = client.post("/workbench/account-snapshot-preview", json={
        "fills": FILL_CSV,
    })
    assert response.status_code == 200, response.text
    assert response.json()["daily_fill_coverage"] is None
    assert response.json()["full_account_verified"] is False
