from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import TradePlan, TradePlanVersion
from app.domain.enums import EntryMode, PlanStatus, PlanVersionState, SetupType, StructureStage
from app.services.trade_plans import TradePlanService


def _base_version_data() -> dict[str, object]:
    return {
        "setup_type": SetupType.C,
        "structure_stage": StructureStage.EARLY,
        "key_support_price": Decimal("10.00"),
        "structure_invalidation_price": Decimal("9.80"),
        "structure_invalidation_condition": "用户确认收盘有效跌破结构低点",
        "entry_mode": EntryMode.PRICE_RANGE,
        "planned_total_position_amount": Decimal(100000),
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
        "remaining_exit_condition": "整体结构转弱后退出剩余仓位",
        "remaining_exit_condition_triggered": False,
    }


def _submit_and_activate(
    session: Session,
    version: TradePlanVersion,
    *,
    with_override: bool = False,
) -> None:
    TradePlanService.submit_for_audit(session, version)
    TradePlanService.activate_version(session, version, with_override=with_override)


def test_new_plan_requires_audit_before_becoming_effective(session: Session) -> None:
    plan, v1 = TradePlanService.create_plan(
        session,
        instrument_code="600000",
        instrument_name="浦发银行",
        version_data=_base_version_data(),
    )

    assert plan.status is PlanStatus.DRAFT
    assert plan.is_active is False
    assert v1.state is PlanVersionState.DRAFT
    assert v1.is_effective is False
    assert TradePlanService.get_effective_version(session, plan.id) is None

    with pytest.raises(ValueError, match="待审计"):
        TradePlanService.activate_version(session, v1)

    TradePlanService.submit_for_audit(session, v1)
    assert v1.state is PlanVersionState.PENDING_AUDIT
    assert v1.is_effective is False
    assert plan.is_active is False

    TradePlanService.activate_version(session, v1)
    assert plan.status is PlanStatus.ACTIVE
    assert plan.is_active is True
    assert v1.state is PlanVersionState.EFFECTIVE
    assert v1.is_effective is True


def test_revision_keeps_v1_until_v2_is_audited_and_activated(session: Session) -> None:
    plan, v1 = TradePlanService.create_plan(
        session,
        instrument_code="600000",
        instrument_name="浦发银行",
        version_data=_base_version_data(),
    )
    _submit_and_activate(session, v1)

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
    assert v2.state is PlanVersionState.DRAFT
    assert v1.key_support_price == Decimal("10.00")
    assert v2.key_support_price == Decimal("10.20")

    TradePlanService.submit_for_audit(session, v2)
    assert TradePlanService.get_effective_version(session, plan.id).id == v1.id

    TradePlanService.activate_version(session, v2)
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


def test_override_reject_and_close_lifecycle_states(session: Session) -> None:
    override_plan, override_version = TradePlanService.create_plan(
        session,
        instrument_code="000001",
        instrument_name="平安银行",
        version_data=_base_version_data(),
    )
    _submit_and_activate(session, override_version, with_override=True)
    assert override_version.state is PlanVersionState.EFFECTIVE_WITH_OVERRIDE
    assert override_version.is_effective is True

    TradePlanService.close_plan(session, override_plan)
    assert override_plan.status is PlanStatus.CLOSED
    assert override_plan.is_active is False
    assert override_version.state is PlanVersionState.CLOSED
    assert override_version.is_effective is False

    rejected_plan, rejected_version = TradePlanService.create_plan(
        session,
        instrument_code="000002",
        instrument_name="万科A",
        version_data=_base_version_data(),
    )
    TradePlanService.submit_for_audit(session, rejected_version)
    TradePlanService.reject_version(session, rejected_version)
    assert rejected_plan.status is PlanStatus.DRAFT
    assert rejected_plan.is_active is False
    assert rejected_version.state is PlanVersionState.REJECTED
    assert rejected_version.is_effective is False


def test_position_size_input_is_normalized_and_core_fields_are_versioned(session: Session) -> None:
    version_data = _base_version_data()
    version_data.pop("planned_total_position_amount")

    _, version = TradePlanService.create_plan(
        session,
        instrument_code="600001",
        instrument_name="邯郸钢铁",
        version_data=version_data,
        account_equity=Decimal(200000),
    )

    assert version.entry_mode is EntryMode.PRICE_RANGE
    assert version.planned_total_position_pct == Decimal(50)
    assert version.planned_total_position_amount == Decimal("100000.0000")
    assert version.remaining_exit_condition_triggered is False

    _submit_and_activate(session, version)
    revision = TradePlanService.create_revision(
        session,
        plan=version.plan,
        changes={"planned_total_position_amount": Decimal(60000)},
        account_equity=Decimal(200000),
    )
    assert revision.planned_total_position_amount == Decimal(60000)
    assert revision.planned_total_position_pct == Decimal("30.0000")


def test_noncritical_note_update_does_not_create_a_new_audit_version(session: Session) -> None:
    plan, v1 = TradePlanService.create_plan(
        session,
        instrument_code="600002",
        instrument_name="齐鲁石化",
        version_data=_base_version_data(),
        user_note="初始备注",
    )
    _submit_and_activate(session, v1)

    TradePlanService.update_note(session, plan, "只改备注，不重审")

    version_count = session.scalar(
        select(func.count(TradePlanVersion.id)).where(TradePlanVersion.plan_id == plan.id)
    )
    assert version_count == 1
    assert plan.user_note == "只改备注，不重审"
    assert v1.state is PlanVersionState.EFFECTIVE
    assert v1.is_effective is True

    with pytest.raises(ValueError, match="不支持的计划版本字段"):
        TradePlanService.create_revision(
            session,
            plan=plan,
            changes={"user_note": "备注不得进入关键版本字段"},
        )


def test_same_instrument_cannot_have_two_active_main_plans(session: Session) -> None:
    first_plan, first_version = TradePlanService.create_plan(
        session,
        instrument_code="600000",
        instrument_name="浦发银行",
        version_data=_base_version_data(),
    )
    _submit_and_activate(session, first_version)
    assert first_plan.is_active is True

    second_plan, second_version = TradePlanService.create_plan(
        session,
        instrument_code="600000",
        instrument_name="浦发银行",
        version_data=_base_version_data(),
    )
    assert second_plan.is_active is False
    TradePlanService.submit_for_audit(session, second_version)

    with pytest.raises(IntegrityError):
        TradePlanService.activate_version(session, second_version)


def test_closed_plan_allows_a_new_main_plan_for_same_instrument(session: Session) -> None:
    plan, first_version = TradePlanService.create_plan(
        session,
        instrument_code="600000",
        instrument_name="浦发银行",
        version_data=_base_version_data(),
    )
    _submit_and_activate(session, first_version)
    TradePlanService.close_plan(session, plan)

    new_plan, new_version = TradePlanService.create_plan(
        session,
        instrument_code="600000",
        instrument_name="浦发银行",
        version_data=_base_version_data(),
    )
    _submit_and_activate(session, new_version)

    assert new_plan.id != plan.id
    assert new_plan.is_active is True
