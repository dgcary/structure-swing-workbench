"""Real PostgreSQL integration: timezone-aware, read-only M8 projections.

The test uses an isolated CI PostgreSQL service with Alembic migrations.
No real brokerage credentials, holdings, or orders are involved.
"""

import os
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import (
    AccountSnapshot,
    ExecutionFill,
    PositionBucketSnapshot,
    PositionSnapshot,
    TradeAction,
    TradePlan,
    TradePlanVersion,
)
from app.domain.enums import (
    ActionStatus,
    ActionType,
    OrderSide,
    PlanStatus,
    PlanVersionState,
    PositionBucketType,
)
from app.workbench.action_date import ActionDateRequest, update_action_planned_date
from app.workbench.overview import build_overview
from app.workbench.persisted import project_persisted
from app.workbench.t_cycle_evidence import MARKET_TZ, project_recorded_t_cycles

PG_TEST_URL = os.environ.get("WORKBENCH_PG_TEST_URL")


@pytest.mark.skipif(not PG_TEST_URL, reason="需要独立的 PostgreSQL 测试数据库")
def test_postgres_migrated_read_only_projection_preserves_timezone_and_fails_closed():
    """A migrated PostgreSQL database must preserve observation provenance."""
    engine = create_engine(PG_TEST_URL)
    try:
        # Never commit fixture records; the dedicated CI database is rolled back.
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                with Session(bind=connection, expire_on_commit=False) as session:
                    now = datetime.now(UTC)
                    captured_at = now - timedelta(minutes=30)
                    plan_at = now - timedelta(hours=2)
                    snapshot = AccountSnapshot(
                        captured_at=captured_at,
                        total_equity=Decimal(200000),
                        available_cash=Decimal(100000),
                        source="manual",
                    )
                    session.add(snapshot)
                    session.flush()
                    position = PositionSnapshot(
                        account_snapshot_id=snapshot.id,
                        instrument_code="600000",
                        instrument_name="测试标的",
                        total_quantity=Decimal(100),
                        market_value=Decimal(1200),
                        broker_cost_price=Decimal(10),
                    )
                    session.add(position)
                    session.flush()
                    session.add_all([
                        PositionBucketSnapshot(
                            position_snapshot_id=position.id,
                            bucket_type=PositionBucketType.CORE,
                            quantity=Decimal(100),
                            strategy_cost_price=Decimal(10),
                        ),
                        PositionBucketSnapshot(
                            position_snapshot_id=position.id,
                            bucket_type=PositionBucketType.T,
                            quantity=Decimal(0),
                        ),
                    ])
                    plan = TradePlan(
                        instrument_code="600000",
                        instrument_name="测试标的",
                        status=PlanStatus.ACTIVE,
                        is_active=True,
                    )
                    session.add(plan)
                    session.flush()
                    version = TradePlanVersion(
                        plan_id=plan.id,
                        version_number=1,
                        state=PlanVersionState.EFFECTIVE,
                        is_effective=True,
                        structure_invalidation_price=Decimal(9),
                        first_target_price=Decimal(12),
                        created_at=plan_at,
                        updated_at=plan_at,
                    )
                    session.add(version)
                    session.flush()
                    snapshot_id, version_id = snapshot.id, version.id

                    # Force a real DB round-trip: SQLite loses timezone offsets;
                    # PostgreSQL TIMESTAMPTZ must return an aware datetime.
                    session.expire_all()
                    stored_snapshot = session.get(AccountSnapshot, snapshot_id)
                    stored_version = session.get(TradePlanVersion, version_id)
                    assert stored_snapshot is not None
                    assert stored_version is not None
                    assert stored_snapshot.captured_at.utcoffset() is not None
                    assert stored_version.updated_at.utcoffset() is not None

                    overview = build_overview(persisted=project_persisted(session))
                    metrics = {row["key"]: row for row in overview["metrics"]}
                    assert metrics["equity"]["value"] == "200000.0000"
                    assert Decimal(metrics["account_risk"]["value"]) == Decimal("0.05")
                    assert metrics["account_risk"]["status"] == "available"
                    assert overview["holdings"][0]["core_quantity"] == "100.0000"
                    assert overview["holdings"][0]["t_quantity"] == "0.0000"
                    assert Decimal(overview["effective_plans"][0]["current_risk"]) == Decimal(100)
                    assert overview["trade_execution_enabled"] is False

                    # A future timestamp cannot certify a real account fact.
                    stored_snapshot.captured_at = now + timedelta(days=1)
                    session.flush()
                    session.expire_all()
                    future_snapshot = build_overview(persisted=project_persisted(session))
                    future_metrics = {row["key"]: row for row in future_snapshot["metrics"]}
                    assert future_metrics["equity"]["status"] == "unavailable"
                    assert future_metrics["account_risk"]["status"] == "unavailable"
                    assert future_snapshot["holdings"] is None

                    # A future plan cannot become an effective displayed plan.
                    session.get(AccountSnapshot, snapshot_id).captured_at = captured_at
                    session.get(TradePlanVersion, version_id).updated_at = now + timedelta(days=1)
                    session.flush()
                    session.expire_all()
                    future_plan = build_overview(persisted=project_persisted(session))
                    assert future_plan["effective_plans"] == []
                    assert future_plan["pending_actions"] == []
                    assert future_plan["audit_results"] == []
                    assert future_plan["trade_execution_enabled"] is False
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


@pytest.mark.skipif(not PG_TEST_URL, reason="需要独立的 PostgreSQL 测试数据库")
def test_postgres_explicit_manual_action_date_roundtrip_never_enables_trading():
    """M8 action dates survive the Alembic migration without becoming orders."""
    engine = create_engine(PG_TEST_URL)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                with Session(bind=connection, expire_on_commit=False) as session:
                    now = datetime.now(UTC)
                    market_today = datetime.now(timezone(timedelta(hours=8))).date()
                    plan = TradePlan(
                        instrument_code="600000", instrument_name="合成测试标的",
                        status=PlanStatus.ACTIVE, is_active=True,
                    )
                    session.add(plan)
                    session.flush()
                    version = TradePlanVersion(
                        plan_id=plan.id, version_number=1,
                        state=PlanVersionState.EFFECTIVE, is_effective=True,
                        created_at=now - timedelta(hours=2),
                        updated_at=now - timedelta(hours=2),
                    )
                    session.add(version)
                    session.flush()
                    action = TradeAction(
                        plan_version_id=version.id,
                        action_type=ActionType.INITIAL_ENTRY,
                        side=OrderSide.BUY, status=ActionStatus.PLANNED,
                        planned_for_date=market_today,
                        created_at=now - timedelta(minutes=20),
                        updated_at=now - timedelta(minutes=20),
                    )
                    session.add(action)
                    session.flush()
                    action_id = action.id
                    session.expire_all()
                    stored = session.get(TradeAction, action_id)
                    assert stored is not None
                    assert stored.planned_for_date == market_today
                    assert stored.updated_at.utcoffset() is not None

                    # A user-entered date must be written and read back from
                    # the migrated PostgreSQL table, not only from a fixture.
                    changed = update_action_planned_date(
                        session, action_id,
                        ActionDateRequest(
                            planned_for_date=(market_today + timedelta(days=1)).isoformat(),
                            expected_as_of=stored.updated_at,
                        ),
                    )
                    assert changed["trade_execution_enabled"] is False
                    session.expire_all()
                    other_day = build_overview(persisted=project_persisted(session))
                    assert other_day["pending_actions"][0]["date_status"] == "other_day"
                    refreshed = session.get(TradeAction, action_id)
                    update_action_planned_date(
                        session, action_id,
                        ActionDateRequest(
                            planned_for_date=market_today.isoformat(),
                            expected_as_of=refreshed.updated_at,
                        ),
                    )
                    session.expire_all()

                    overview = build_overview(persisted=project_persisted(session))
                    assert len(overview["pending_actions"]) == 1
                    row = overview["pending_actions"][0]
                    assert row["date_status"] == "today"
                    assert row["planned_for_date"] == market_today.isoformat()
                    assert row["executable"] is False
                    assert overview["trade_execution_enabled"] is False

                    stored.planned_for_date = market_today - timedelta(days=1)
                    session.flush()
                    session.expire_all()
                    past = build_overview(persisted=project_persisted(session))
                    assert past["pending_actions"][0]["date_status"] == "other_day"

                    session.get(TradeAction, action_id).planned_for_date = None
                    session.flush()
                    session.expire_all()
                    unknown = build_overview(persisted=project_persisted(session))
                    assert unknown["pending_actions"][0]["date_status"] == "unverified"
                    assert unknown["pending_actions"][0]["planned_for_date"] is None

                    # A recorded fill must make the intended action date immutable,
                    # even if an inconsistent legacy row still says PLANNED.
                    session.add(ExecutionFill(
                        action_id=action_id, side=OrderSide.BUY,
                        quantity=Decimal(10), price=Decimal(10),
                        fee=Decimal(0), executed_at=now - timedelta(minutes=5),
                        source="manual",
                    ))
                    session.flush()
                    session.expire_all()
                    recorded = session.get(TradeAction, action_id)
                    with pytest.raises(HTTPException) as rejected:
                        update_action_planned_date(
                            session, action_id,
                            ActionDateRequest(
                                planned_for_date=market_today.isoformat(),
                                expected_as_of=recorded.updated_at,
                            ),
                        )
                    assert rejected.value.status_code == 409
                    session.expire_all()
                    assert session.get(TradeAction, action_id).planned_for_date is None
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


@pytest.mark.skipif(not PG_TEST_URL, reason="需要独立的 PostgreSQL 测试数据库")
def test_postgres_recorded_t_cycle_fills_are_dated_but_not_broker_complete():
    """M8 can prove a recorded split-fill cycle, never daily broker completeness."""
    engine = create_engine(PG_TEST_URL)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                with Session(bind=connection, expire_on_commit=False) as session:
                    now = datetime.now(UTC)
                    first_at = now - timedelta(minutes=4)
                    market_day = first_at.astimezone(MARKET_TZ).date()
                    plan = TradePlan(
                        instrument_code="600000", instrument_name="合成T测试",
                        status=PlanStatus.ACTIVE, is_active=True,
                    )
                    session.add(plan)
                    session.flush()
                    version = TradePlanVersion(
                        plan_id=plan.id, version_number=1,
                        state=PlanVersionState.EFFECTIVE, is_effective=True,
                        created_at=now - timedelta(hours=1),
                        updated_at=now - timedelta(hours=1),
                    )
                    session.add(version)
                    session.flush()
                    sell = TradeAction(
                        plan_version_id=version.id,
                        action_type=ActionType.POSITIVE_T_SELL,
                        side=OrderSide.SELL, status=ActionStatus.FILLED,
                        t_cycle_key="cycle-test",
                    )
                    buy = TradeAction(
                        plan_version_id=version.id,
                        action_type=ActionType.POSITIVE_T_BUYBACK,
                        side=OrderSide.BUY, status=ActionStatus.FILLED,
                        t_cycle_key="cycle-test",
                    )
                    session.add_all([sell, buy])
                    session.flush()
                    session.add_all([
                        ExecutionFill(
                            action_id=sell.id, side=OrderSide.SELL,
                            quantity=Decimal(40), price=Decimal(10),
                            fee=Decimal(0), executed_at=first_at, source="manual",
                            external_execution_id="shared-with-ordinary",
                        ),
                        ExecutionFill(
                            action_id=sell.id, side=OrderSide.SELL,
                            quantity=Decimal(60), price=Decimal(10),
                            fee=Decimal(0), executed_at=first_at + timedelta(seconds=1),
                            source="manual",
                        ),
                        ExecutionFill(
                            action_id=buy.id, side=OrderSide.BUY,
                            quantity=Decimal(100), price=Decimal(9),
                            fee=Decimal(0), executed_at=first_at + timedelta(seconds=2),
                            source="manual",
                        ),
                    ])
                    session.flush()
                    session.expire_all()
                    cycles = project_recorded_t_cycles(session, market_day)
                    assert len(cycles) == 1
                    assert cycles[0]["state"] == "closed"
                    assert cycles[0]["opening_quantity"] == "100.0000"
                    assert cycles[0]["closing_quantity"] == "100.0000"
                    assert cycles[0]["broker_reconciled"] is False
                    assert cycles[0]["as_of"] is not None
                    assert len(cycles[0]["sources"]) == 3

                    # Recorded fills do not prove a broker-complete day or T+1.
                    overview = build_overview(persisted={"t_cycle_evidence": cycles})
                    metrics = {row["key"]: row for row in overview["metrics"]}
                    assert metrics["t_cycles_today"]["status"] == "unavailable"
                    assert metrics["open_t_cycles"]["status"] == "unavailable"
                    assert overview["trade_execution_enabled"] is False

                    # A non-T fill with the same source-scoped broker ID
                    # invalidates the T evidence after a real database round-trip.
                    ordinary = TradeAction(
                        plan_version_id=version.id,
                        action_type=ActionType.ORDINARY_ADD,
                        side=OrderSide.BUY, status=ActionStatus.FILLED,
                    )
                    session.add(ordinary)
                    session.flush()
                    session.add(ExecutionFill(
                        action_id=ordinary.id, side=OrderSide.BUY,
                        quantity=Decimal(40), price=Decimal(10),
                        fee=Decimal(0), executed_at=first_at + timedelta(seconds=3),
                        source="manual",
                        external_execution_id="shared-with-ordinary",
                    ))
                    session.flush()
                    session.expire_all()
                    reused = project_recorded_t_cycles(session, market_day)
                    assert len(reused) == 1
                    assert reused[0]["state"] == "conflict"
                    assert reused[0]["broker_reconciled"] is False

                    session.add(ExecutionFill(
                        action_id=buy.id, side=OrderSide.BUY,
                        quantity=Decimal(1), price=Decimal(9),
                        fee=Decimal(0), executed_at=first_at + timedelta(seconds=3),
                        source="manual",
                    ))
                    session.flush()
                    session.expire_all()
                    conflict = project_recorded_t_cycles(session, market_day)
                    assert conflict[0]["state"] == "conflict"
                    assert conflict[0]["opening_quantity"] is None
            finally:
                transaction.rollback()
    finally:
        engine.dispose()
