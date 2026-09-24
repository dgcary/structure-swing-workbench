from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import TradePlan, TradePlanVersion
from app.domain.enums import PlanVersionState, SetupType, StructureStage
from app.services.trade_plans import TradePlanService


def _base_version_data() -> dict[str, object]:
    return {
        "setup_type": SetupType.C,
        "structure_stage": StructureStage.EARLY,
        "key_support_price": Decimal("10.00"),
        "structure_invalidation_price": Decimal("9.80"),
        "structure_invalidation_condition": "用户确认收盘有效跌破结构低点",
        "planned_total_position_pct": Decimal(50),
        "initial_entry_price_low": Decimal("10.10"),
        "initial_entry_price_high": Decimal("10.30"),
        "initial_entry_pct": Decimal(40),
        "confirmation_add_enabled": True,
        "confirmation_trigger_price": Decimal("10.80"),
        "confirmation_add_pct": Decimal(30),
        "t_reserve_pct": Decimal(30),
        "first_target_price": Decimal("12.00"),
        "first_target_reduce_pct": Decimal(50),
    }


def test_revision_keeps_v1_until_v2_is_activated(session: Session) -> None:
    plan, v1 = TradePlanService.create_plan(
        session,
        instrument_code="600000",
        instrument_name="浦发银行",
        version_data=_base_version_data(),
    )

    v2 = TradePlanService.create_revision(
        session,
        plan=plan,
        changes={"key_support_price": Decimal("10.20")},
        reason="用户调整关键支撑",
    )

    assert v1.is_effective is True
    assert v1.state is PlanVersionState.EFFECTIVE
    assert v2.version_number == 2
    assert v2.based_on_version_id == v1.id
    assert v2.is_effective is False
    assert v2.state is PlanVersionState.PENDING_AUDIT
    assert v1.key_support_price == Decimal("10.00")
    assert v2.key_support_price == Decimal("10.20")

    TradePlanService.activate_version(session, v2)
    session.flush()

    versions = list(
        session.scalars(
            select(TradePlanVersion)
            .where(TradePlanVersion.plan_id == plan.id)
            .order_by(TradePlanVersion.version_number)
        )
    )
    assert [version.version_number for version in versions] == [1, 2]
    assert versions[0].key_support_price == Decimal("10.00")
    assert versions[0].state is PlanVersionState.SUPERSEDED
    assert versions[0].is_effective is False
    assert versions[1].state is PlanVersionState.EFFECTIVE
    assert versions[1].is_effective is True


def test_same_instrument_cannot_have_two_active_main_plans(session: Session) -> None:
    TradePlanService.create_plan(
        session,
        instrument_code="600000",
        instrument_name="浦发银行",
        version_data=_base_version_data(),
    )
    session.flush()

    duplicate = TradePlan(
        instrument_code="600000",
        instrument_name="浦发银行",
        is_active=True,
    )
    session.add(duplicate)

    with pytest.raises(IntegrityError):
        session.flush()


def test_closed_plan_allows_a_new_main_plan_for_same_instrument(session: Session) -> None:
    plan, _ = TradePlanService.create_plan(
        session,
        instrument_code="600000",
        instrument_name="浦发银行",
        version_data=_base_version_data(),
    )
    TradePlanService.close_plan(session, plan)

    new_plan, _ = TradePlanService.create_plan(
        session,
        instrument_code="600000",
        instrument_name="浦发银行",
        version_data=_base_version_data(),
    )

    assert new_plan.id != plan.id
    assert new_plan.is_active is True
