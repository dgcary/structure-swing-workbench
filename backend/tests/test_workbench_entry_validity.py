"""§15.43: entry-plan expiry does not silently hide a still-held main plan.

All records are synthetic. An observed fill/snapshot is display evidence,
not a broker completeness certificate or an authorization to trade.
"""

import os
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import (
    AccountSnapshot,
    ExecutionFill,
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
)
from app.workbench.overview import build_overview
from app.workbench.persisted import project_persisted

PG_TEST_URL = os.environ.get("WORKBENCH_PG_TEST_URL")


def _expired_plan(session):
    market_today = datetime.now(timezone(timedelta(hours=8))).date()
    plan = TradePlan(
        instrument_code="600000", instrument_name="合成持仓",
        status=PlanStatus.ACTIVE, is_active=True,
    )
    session.add(plan)
    session.flush()
    version = TradePlanVersion(
        plan_id=plan.id, version_number=1,
        state=PlanVersionState.EFFECTIVE, is_effective=True,
        valid_until=market_today - timedelta(days=2),
        structure_invalidation_price=Decimal(9),
        created_at=datetime.now(UTC) - timedelta(days=4),
        updated_at=datetime.now(UTC) - timedelta(days=4),
    )
    session.add(version)
    session.flush()
    return version


def test_expired_unentered_plan_is_not_shown_as_effective(session):
    _expired_plan(session)
    overview = build_overview(persisted=project_persisted(session))
    assert overview["effective_plans"] == []
    assert overview["trade_execution_enabled"] is False


@pytest.mark.skipif(not PG_TEST_URL, reason="需要独立的 PostgreSQL 测试数据库")
def test_postgres_entered_plan_stays_visible_after_entry_deadline_only_with_evidence():
    engine = create_engine(PG_TEST_URL)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                with Session(bind=connection, expire_on_commit=False) as session:
                    now = datetime.now(UTC)
                    version = _expired_plan(session)
                    snapshot = AccountSnapshot(
                        captured_at=now - timedelta(minutes=10),
                        total_equity=Decimal(100000),
                        available_cash=Decimal(80000),
                        source="manual",
                    )
                    session.add(snapshot)
                    session.flush()
                    position = PositionSnapshot(
                        account_snapshot_id=snapshot.id,
                        instrument_code="600000",
                        instrument_name="合成持仓",
                        total_quantity=Decimal(100),
                        market_value=Decimal(1200),
                    )
                    session.add(position)
                    action = TradeAction(
                        plan_version_id=version.id,
                        action_type=ActionType.INITIAL_ENTRY,
                        side=OrderSide.BUY,
                        status=ActionStatus.FILLED,
                    )
                    session.add(action)
                    session.flush()
                    fill = ExecutionFill(
                        action_id=action.id, side=OrderSide.BUY,
                        quantity=Decimal(100), price=Decimal(10),
                        fee=Decimal(0),
                        executed_at=now - timedelta(hours=1),
                        source="manual",
                    )
                    session.add(fill)
                    session.flush()

                    def projected():
                        session.expire_all()
                        return build_overview(persisted=project_persisted(session))

                    held = projected()
                    assert len(held["effective_plans"]) == 1
                    assert held["effective_plans"][0]["id"] == version.id
                    assert "入场有效期不再自动终止" in held["effective_plans"][0]["warning"]
                    assert held["effective_plans"][0]["current_risk"] is None
                    assert held["trade_execution_enabled"] is False

                    # A positive snapshot alone is not proof of an initial buy.
                    session.delete(session.get(ExecutionFill, fill.id))
                    session.flush()
                    assert projected()["effective_plans"] == []

                    # A future fill cannot justify a historical holding.
                    future = ExecutionFill(
                        action_id=action.id, side=OrderSide.BUY,
                        quantity=Decimal(100), price=Decimal(10),
                        fee=Decimal(0),
                        executed_at=now + timedelta(days=1),
                        source="manual",
                    )
                    session.add(future)
                    session.flush()
                    assert projected()["effective_plans"] == []

                    # A recorded fill alone is not proof of a current holding.
                    session.get(ExecutionFill, future.id).executed_at = (
                        now - timedelta(hours=1)
                    )
                    session.get(PositionSnapshot, position.id).total_quantity = Decimal(0)
                    session.flush()
                    assert projected()["effective_plans"] == []
            finally:
                transaction.rollback()
    finally:
        engine.dispose()
