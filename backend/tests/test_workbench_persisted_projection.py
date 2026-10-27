"""M8 persisted projections are historical read-only evidence, not trading permission."""

from datetime import UTC, datetime
from decimal import Decimal

from app.db.models import (
    AccountSnapshot,
    AuditResult,
    PositionBucketSnapshot,
    PositionSnapshot,
    TradeAction,
    TradePlan,
    TradePlanVersion,
)
from app.domain.enums import (
    ActionStatus,
    ActionType,
    AuditLevel,
    OrderSide,
    PlanStatus,
    PlanVersionState,
    PositionBucketType,
)
from app.workbench.overview import build_overview
from app.workbench.persisted import _observed_at, project_persisted


def test_empty_database_is_unknown_not_zero_or_audit_pass(session) -> None:
    projection = project_persisted(session)
    overview = build_overview(persisted=projection)
    assert overview["effective_plans"] == []
    assert overview["pending_actions"] == []
    assert overview["audit_results"] == []
    assert overview["holdings"] is None
    assert all(metric["status"] == "unavailable" for metric in overview["metrics"])
    assert overview["trade_execution_enabled"] is False


def test_persisted_plan_action_and_hard_fail_never_enable_execution(session) -> None:
    plan = TradePlan(
        instrument_code="600000", instrument_name="人工标的",
        status=PlanStatus.ACTIVE, is_active=True,
    )
    session.add(plan)
    session.flush()
    version = TradePlanVersion(
        plan_id=plan.id, version_number=1,
        state=PlanVersionState.EFFECTIVE, is_effective=True,
        structure_invalidation_price=Decimal(9),
        first_target_price=Decimal(13),
    )
    session.add(version)
    session.flush()
    action = TradeAction(
        plan_version_id=version.id, action_type=ActionType.INITIAL_ENTRY,
        side=OrderSide.BUY, status=ActionStatus.AUDITED,
        planned_price_low=Decimal(10),
        planned_price_high=Decimal(11),
    )
    session.add(action)
    session.flush()
    session.add(AuditResult(
        action_id=action.id, level=AuditLevel.HARD_FAIL,
        summary="结构失效后禁止扩大风险", engine_version="m2-audit",
    ))
    session.flush()

    overview = build_overview(persisted=project_persisted(session))
    assert overview["trade_execution_enabled"] is False
    assert len(overview["effective_plans"]) == 1
    assert Decimal(overview["effective_plans"][0]["invalidation_price"]) == Decimal(9)
    assert Decimal(overview["effective_plans"][0]["first_target_price"]) == Decimal(13)
    assert overview["pending_actions"][0]["executable"] is False
    assert overview["audit_results"][0]["level"] == "hard_fail"
    assert overview["audit_results"][0]["executable"] is False
    assert overview["metrics"][4]["value"] is None


def test_naive_database_times_cannot_be_presented_as_sourced_account(session) -> None:
    snapshot = AccountSnapshot(
        captured_at=datetime(2026, 10, 22, 10, 0),
        total_equity=Decimal(100000), available_cash=Decimal(20000),
        source="manual",
    )
    session.add(snapshot)
    session.flush()
    position = PositionSnapshot(
        account_snapshot_id=snapshot.id, instrument_code="600000",
        instrument_name="人工标的", total_quantity=Decimal(100),
        market_value=Decimal(1200), broker_cost_price=Decimal(10),
    )
    session.add(position)
    session.flush()
    session.add(PositionBucketSnapshot(
        position_snapshot_id=position.id, bucket_type=PositionBucketType.CORE,
        quantity=Decimal(70),
    ))
    session.add(PositionBucketSnapshot(
        position_snapshot_id=position.id, bucket_type=PositionBucketType.T,
        quantity=Decimal(30),
    ))
    session.flush()
    overview = build_overview(persisted=project_persisted(session))
    assert overview["holdings"] is None
    assert all(metric["status"] == "unavailable" for metric in overview["metrics"])
    assert _observed_at(datetime(2026, 10, 22, 10, 0)) is None
    assert _observed_at(datetime(2026, 10, 22, 10, 0, tzinfo=UTC)) is not None
