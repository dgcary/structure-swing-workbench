"""M8 formal-action date entry is opt-in and never grants trade permission."""
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import main as api
from app.core.config import Settings
from app.db.models import TradePlan, TradePlanVersion
from app.domain.enums import ActionStatus, PlanVersionState
from app.workbench.action_date import ActionDateRequest, update_action_planned_date


class _Session:
    def __init__(self):
        self.action = SimpleNamespace(
            id=str(uuid4()), plan_version_id="version",
            status=ActionStatus.PLANNED,
            updated_at=datetime.now(UTC) - timedelta(minutes=10),
            planned_for_date=None,
        )
        self.version = SimpleNamespace(
            plan_id="plan", is_effective=True,
            state=PlanVersionState.EFFECTIVE, valid_until=None,
            updated_at=datetime.now(UTC) - timedelta(hours=2),
        )
        self.plan = SimpleNamespace(is_active=True)
        self.flushed = False

    def scalar(self, _statement):
        return self.action

    def get(self, model, _identifier):
        if model is TradePlanVersion:
            return self.version
        if model is TradePlan:
            return self.plan
        raise AssertionError("unexpected model")

    def flush(self):
        self.flushed = True
        self.action.updated_at = datetime.now(UTC)


def _payload(session, date="2026-10-28"):
    return ActionDateRequest(
        planned_for_date=date, expected_as_of=session.action.updated_at,
    )


def test_explicit_date_and_clear_never_authorize_execution():
    session = _Session()
    first = update_action_planned_date(session, session.action.id, _payload(session))
    assert session.flushed
    assert first["saved"] is True
    assert first["planned_for_date"] == "2026-10-28"
    assert first["trade_execution_enabled"] is False
    assert session.action.status is ActionStatus.PLANNED

    cleared = update_action_planned_date(
        session, session.action.id, _payload(session, None),
    )
    assert cleared["planned_for_date"] is None
    assert cleared["trade_execution_enabled"] is False


@pytest.mark.parametrize("problem", [
    "stale", "audited", "expired", "future_version", "naive_action", "inactive",
])
def test_conflict_or_untrusted_record_fails_closed(problem):
    session = _Session()
    payload = _payload(session)
    if problem == "stale":
        payload.expected_as_of -= timedelta(minutes=1)
    elif problem == "audited":
        session.action.status = ActionStatus.AUDITED
    elif problem == "expired":
        session.version.valid_until = (
            datetime.now(timezone(timedelta(hours=8))).date() - timedelta(days=1)
        )
    elif problem == "future_version":
        session.version.updated_at = datetime.now(UTC) + timedelta(days=1)
    elif problem == "naive_action":
        session.action.updated_at = session.action.updated_at.replace(tzinfo=None)
    elif problem == "inactive":
        session.plan.is_active = False
    with pytest.raises(HTTPException) as exc:
        update_action_planned_date(session, session.action.id, payload)
    assert exc.value.status_code == 409
    assert not session.flushed
    assert session.action.planned_for_date is None


@pytest.mark.parametrize("bad_date", ["2026-02-30", "20261027", 20261027, "明天"])
def test_date_is_explicit_iso_only(bad_date):
    with pytest.raises(ValidationError):
        ActionDateRequest(planned_for_date=bad_date, expected_as_of=datetime.now(UTC))


def test_missing_timezone_rejected():
    with pytest.raises(ValidationError):
        ActionDateRequest(
            planned_for_date="2026-10-28", expected_as_of=datetime(2026, 10, 27),
        )


def test_date_write_endpoint_disabled_by_default(monkeypatch):
    monkeypatch.setattr(api, "settings", Settings(
        workbench_persisted_read_enabled=False,
        workbench_action_date_write_enabled=False,
    ))
    response = TestClient(api.app).put(
        "/workbench/actions/" + str(uuid4()) + "/planned-date",
        json={"planned_for_date": "2026-10-28", "expected_as_of": datetime.now(UTC).isoformat()},
    )
    assert response.status_code == 404


def test_date_write_requires_strong_secret_and_bearer(monkeypatch):
    url = "/workbench/actions/" + str(uuid4()) + "/planned-date"
    payload = {"planned_for_date": "2026-10-28",
               "expected_as_of": datetime.now(UTC).isoformat()}
    monkeypatch.setattr(api, "settings", Settings(
        workbench_persisted_read_enabled=True,
        workbench_action_date_write_enabled=True,
        workbench_action_date_write_token="short",
    ))
    assert TestClient(api.app).put(url, json=payload).status_code == 503
    monkeypatch.setattr(api, "settings", Settings(
        workbench_persisted_read_enabled=True,
        workbench_action_date_write_enabled=True,
        workbench_action_date_write_token="x" * 40,
    ))
    client = TestClient(api.app)
    assert client.put(url, json=payload).status_code == 401
    assert client.put(
        url, json=payload, headers={"Authorization": "Bearer incorrect"},
    ).status_code == 401
