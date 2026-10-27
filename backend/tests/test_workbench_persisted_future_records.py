"""M8 never presents future-dated persisted actions/audits as observed facts."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from app.db.models import AuditResult, TradeAction
from app.domain.enums import ActionStatus, ActionType, AuditLevel, PlanVersionState
from app.workbench.overview import build_overview
from app.workbench.persisted import project_persisted


class _ReadSession:
    def __init__(self, action_time, audit_time):
        now = datetime.now(UTC)
        self.version = SimpleNamespace(
            id="version-1", version_number=1,
            state=PlanVersionState.EFFECTIVE,
            updated_at=now - timedelta(hours=2), valid_until=None,
            structure_invalidation_price=Decimal("9"),
            first_target_price=Decimal("12"),
        )
        self.plan = SimpleNamespace(
            instrument_code="600000", instrument_name="人工标的",
        )
        self.action = SimpleNamespace(
            id="action-1", action_type=ActionType.INITIAL_ENTRY,
            status=ActionStatus.PLANNED,
            planned_price_low=Decimal("10"),
            planned_price_high=Decimal("11"),
            updated_at=action_time,
        )
        self.audit = SimpleNamespace(
            id="audit-1", level=AuditLevel.HARD_FAIL,
            summary="仅用于测试的历史审计", engine_version="m2",
            created_at=audit_time,
        )
        self.audit_reads = 0

    def scalar(self, _statement):
        return None

    def execute(self, _statement):
        return [(self.version, self.plan)]

    def scalars(self, statement):
        entity = statement.column_descriptions[0]["entity"]
        if entity is TradeAction:
            return iter([self.action])
        if entity is AuditResult:
            self.audit_reads += 1
            return iter([self.audit] if self.audit_reads == 1 else [])
        return iter([])


def _metric(overview, key):
    return next(row for row in overview["metrics"] if row["key"] == key)


def test_future_action_cannot_be_shown_as_pending_or_feed_action_audit():
    now = datetime.now(UTC)
    session = _ReadSession(now + timedelta(days=1), now - timedelta(hours=1))
    overview = build_overview(persisted=project_persisted(session))
    assert len(overview["effective_plans"]) == 1
    assert overview["pending_actions"] == []
    assert overview["audit_results"] == []
    assert _metric(overview, "highest_audit")["status"] == "unavailable"
    assert overview["trade_execution_enabled"] is False


def test_future_audit_cannot_be_shown_as_completed_or_raise_severity():
    now = datetime.now(UTC)
    session = _ReadSession(now - timedelta(hours=1), now + timedelta(days=1))
    overview = build_overview(persisted=project_persisted(session))
    assert len(overview["pending_actions"]) == 1
    assert overview["pending_actions"][0]["executable"] is False
    assert overview["audit_results"] == []
    assert _metric(overview, "highest_audit")["status"] == "unavailable"
    assert overview["trade_execution_enabled"] is False


def test_dated_historical_action_and_audit_stay_read_only():
    now = datetime.now(UTC)
    session = _ReadSession(now - timedelta(hours=1), now - timedelta(minutes=30))
    overview = build_overview(persisted=project_persisted(session))
    assert len(overview["pending_actions"]) == 1
    assert len(overview["audit_results"]) == 1
    assert _metric(overview, "highest_audit")["value"] == "硬性失败"
    assert overview["pending_actions"][0]["executable"] is False
    assert overview["audit_results"][0]["executable"] is False
    assert overview["trade_execution_enabled"] is False
