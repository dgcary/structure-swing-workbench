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
    assert overview["attribution_pending_plans"] == []
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
                    assert held["attribution_pending_plans"] == []
                    assert held["effective_plans"][0]["id"] == version.id
                    assert "入场有效期不再自动终止" in held["effective_plans"][0]["warning"]
                    assert held["effective_plans"][0]["current_risk"] is None
                    assert held["trade_execution_enabled"] is False

                    # A historical snapshot cannot certify ownership after
                    # subsequent fills. Both full and partial exits invalidate
                    # its as-of quantity, even when the snapshot still says 100.
                    late_sell = TradeAction(
                        plan_version_id=version.id,
                        action_type=ActionType.REDUCE,
                        side=OrderSide.SELL, status=ActionStatus.FILLED,
                    )
                    session.add(late_sell)
                    session.flush()
                    late_sell_fill = ExecutionFill(
                        action_id=late_sell.id, side=OrderSide.SELL,
                        quantity=Decimal(100), price=Decimal(11),
                        fee=Decimal(0), executed_at=now - timedelta(minutes=5),
                        source="manual",
                    )
                    session.add(late_sell_fill)
                    session.flush()
                    after_full_exit = projected()
                    assert after_full_exit["effective_plans"] == []
                    pending = after_full_exit["attribution_pending_plans"]
                    assert len(pending) == 1
                    assert pending[0]["id"] == version.id
                    assert pending[0]["attribution_status"] == "unverified"
                    assert pending[0]["current_risk"] is None
                    assert "归属待核验" in pending[0]["warning"]
                    assert after_full_exit["trade_execution_enabled"] is False
                    assert next(metric for metric in after_full_exit["metrics"] if metric["key"] == "account_risk")["status"] == "unavailable"
                    late_sell_fill.quantity = Decimal(40)
                    session.flush()
                    assert projected()["effective_plans"] == []
                    session.delete(late_sell_fill)
                    session.delete(late_sell)
                    session.flush()
                    assert len(projected()["effective_plans"]) == 1

                    # A later same-plan buy is also unaccounted for. Compare
                    # instants in UTC, not their differing timezone offsets.
                    late_buy = TradeAction(
                        plan_version_id=version.id,
                        action_type=ActionType.ORDINARY_ADD,
                        side=OrderSide.BUY, status=ActionStatus.FILLED,
                    )
                    session.add(late_buy)
                    session.flush()
                    late_buy_fill = ExecutionFill(
                        action_id=late_buy.id, side=OrderSide.BUY,
                        quantity=Decimal(20), price=Decimal(11),
                        fee=Decimal(0),
                        executed_at=(
                            snapshot.captured_at.astimezone(
                                timezone(timedelta(hours=8))
                            ) + timedelta(microseconds=1)
                        ),
                        source="manual",
                    )
                    session.add(late_buy_fill)
                    session.flush()
                    assert projected()["effective_plans"] == []
                    # Exact snapshot-time fills may be reconciled if the
                    # snapshot quantity already includes them.
                    late_buy_fill.executed_at = snapshot.captured_at
                    position.total_quantity = Decimal(120)
                    session.flush()
                    assert len(projected()["effective_plans"]) == 1
                    late_buy_fill.executed_at = (
                        snapshot.captured_at + timedelta(microseconds=1)
                    )
                    session.flush()
                    assert projected()["effective_plans"] == []
                    # A newer snapshot that covers every recorded fill restores
                    # the historical as-of attribution (not broker certification).
                    snapshot.captured_at = now - timedelta(minutes=1)
                    session.flush()
                    after_reconciliation = projected()
                    assert len(after_reconciliation["effective_plans"]) == 1
                    assert after_reconciliation["attribution_pending_plans"] == []
                    assert after_reconciliation["trade_execution_enabled"] is False
                    assert next(metric for metric in after_reconciliation["metrics"] if metric["key"] == "account_risk")["status"] == "unavailable"
                    session.delete(late_buy_fill)
                    session.delete(late_buy)
                    snapshot.captured_at = now - timedelta(minutes=10)
                    position.total_quantity = Decimal(100)
                    session.flush()
                    assert len(projected()["effective_plans"]) == 1

                    # A matching symbol is insufficient when plan inventory
                    # cannot be reconciled with the recorded fills.
                    position.total_quantity = Decimal(120)
                    session.flush()
                    assert projected()["effective_plans"] == []
                    position.total_quantity = Decimal(100)
                    session.flush()
                    assert len(projected()["effective_plans"]) == 1

                    # Partial sell leaves 60 shares attributable to this plan
                    # only when the snapshot also records exactly 60.
                    sell = TradeAction(
                        plan_version_id=version.id,
                        action_type=ActionType.REDUCE,
                        side=OrderSide.SELL, status=ActionStatus.PARTIALLY_FILLED,
                    )
                    session.add(sell)
                    session.flush()
                    partial = ExecutionFill(
                        action_id=sell.id, side=OrderSide.SELL,
                        quantity=Decimal(40), price=Decimal(11),
                        fee=Decimal(0), executed_at=now - timedelta(minutes=40),
                        source="manual",
                    )
                    session.add(partial)
                    position.total_quantity = Decimal(60)
                    session.flush()
                    assert len(projected()["effective_plans"]) == 1

                    # A second plan for the same stock with its own recorded
                    # buy makes the ownership of this snapshot ambiguous.
                    other_plan = TradePlan(
                        instrument_code="600000", instrument_name="合成再次入场",
                        status=PlanStatus.CLOSED, is_active=False,
                    )
                    session.add(other_plan)
                    session.flush()
                    other_version = TradePlanVersion(
                        plan_id=other_plan.id, version_number=1,
                        state=PlanVersionState.CLOSED, is_effective=False,
                    )
                    session.add(other_version)
                    session.flush()
                    other_action = TradeAction(
                        plan_version_id=other_version.id,
                        action_type=ActionType.INITIAL_ENTRY,
                        side=OrderSide.BUY, status=ActionStatus.FILLED,
                    )
                    session.add(other_action)
                    session.flush()
                    other_fill = ExecutionFill(
                        action_id=other_action.id, side=OrderSide.BUY,
                        quantity=Decimal(40), price=Decimal(12),
                        fee=Decimal(0), executed_at=now - timedelta(minutes=20),
                        source="manual",
                    )
                    session.add(other_fill)
                    session.flush()
                    assert projected()["effective_plans"] == []
                    # Cross-plan activity *after* the latest snapshot must
                    # also prevent an old plan being shown as currently held.
                    other_fill.executed_at = now - timedelta(minutes=5)
                    session.flush()
                    assert projected()["effective_plans"] == []
                    session.delete(other_fill)
                    session.flush()
                    assert len(projected()["effective_plans"]) == 1

                    # A completed exit leaves no inventory for the old plan;
                    # a positive symbol snapshot must not resurrect it.
                    full_exit = ExecutionFill(
                        action_id=sell.id, side=OrderSide.SELL,
                        quantity=Decimal(60), price=Decimal(11),
                        fee=Decimal(0), executed_at=now - timedelta(minutes=30),
                        source="manual",
                    )
                    session.add(full_exit)
                    position.total_quantity = Decimal(100)
                    session.flush()
                    assert projected()["effective_plans"] == []

                    # Re-entering the same symbol after complete exit must
                    # use a new plan ID; an old plan cannot be resurrected.
                    reentry_action = TradeAction(
                        plan_version_id=version.id,
                        action_type=ActionType.INITIAL_ENTRY,
                        side=OrderSide.BUY, status=ActionStatus.FILLED,
                    )
                    session.add(reentry_action)
                    session.flush()
                    reentry_fill = ExecutionFill(
                        action_id=reentry_action.id, side=OrderSide.BUY,
                        quantity=Decimal(100), price=Decimal(12),
                        fee=Decimal(0), executed_at=now - timedelta(minutes=15),
                        source="manual",
                    )
                    session.add(reentry_fill)
                    session.flush()
                    assert projected()["effective_plans"] == []
                    session.delete(reentry_fill)
                    session.delete(full_exit)
                    session.delete(partial)
                    session.flush()
                    assert len(projected()["effective_plans"]) == 1

                    # A positive snapshot alone is not proof of an initial buy.
                    session.delete(session.get(ExecutionFill, fill.id))
                    session.flush()
                    no_first_buy = projected()
                    assert no_first_buy["effective_plans"] == []
                    assert no_first_buy["attribution_pending_plans"] == []

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
