from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.models import AuditResult, ExecutionFill, ManualOverride, TradeAction
from app.domain.enums import ActionType, AuditLevel, OrderSide
from app.services.trade_plans import TradePlanService


def _create_plan(session: Session):
    return TradePlanService.create_plan(
        session,
        instrument_code="000001",
        instrument_name="平安银行",
        version_data={
            "initial_entry_price_low": Decimal("10.00"),
            "initial_entry_price_high": Decimal("10.20"),
            "structure_invalidation_price": Decimal("9.50"),
        },
    )


def test_action_can_own_multiple_real_fills_without_mutating_plan(session: Session) -> None:
    plan, version = _create_plan(session)
    original_low = version.initial_entry_price_low
    original_high = version.initial_entry_price_high

    action = TradeAction(
        plan_id=plan.id,
        plan_version_id=version.id,
        action_type=ActionType.INITIAL_ENTRY,
        side=OrderSide.BUY,
        planned_price_low=Decimal("10.00"),
        planned_price_high=Decimal("10.20"),
        planned_quantity=Decimal(1000),
    )
    action.fills.extend(
        [
            ExecutionFill(
                side=OrderSide.BUY,
                quantity=Decimal(400),
                price=Decimal("10.08"),
                fee=Decimal("1.20"),
                executed_at=datetime(2026, 9, 24, 9, 35, tzinfo=UTC),
            ),
            ExecutionFill(
                side=OrderSide.BUY,
                quantity=Decimal(600),
                price=Decimal("10.12"),
                fee=Decimal("1.80"),
                executed_at=datetime(2026, 9, 24, 9, 36, tzinfo=UTC),
            ),
        ]
    )
    session.add(action)
    session.flush()

    assert len(action.fills) == 2
    assert sum(fill.quantity for fill in action.fills) == Decimal(1000)
    assert version.initial_entry_price_low == original_low
    assert version.initial_entry_price_high == original_high


def test_audit_and_override_point_to_exact_version_and_action(session: Session) -> None:
    plan, version = _create_plan(session)
    action = TradeAction(
        plan_id=plan.id,
        plan_version_id=version.id,
        action_type=ActionType.INITIAL_ENTRY,
        side=OrderSide.BUY,
    )
    session.add(action)
    session.flush()

    audit = AuditResult(
        plan_version_id=version.id,
        action_id=action.id,
        level=AuditLevel.OVERRIDABLE_FAIL,
        summary="模型关系测试，不包含M2规则判断",
        details={"source": "unit-test"},
    )
    audit.overrides.append(ManualOverride(reason="用户确认继续，仅用于模型关系测试"))
    session.add(audit)
    session.flush()

    assert audit.plan_version_id == version.id
    assert audit.action_id == action.id
    assert audit.overrides[0].audit_result_id == audit.id
    assert audit.overrides[0].reason.startswith("用户确认")
