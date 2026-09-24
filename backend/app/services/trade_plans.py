from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import utc_now
from app.db.models import TradePlan, TradePlanVersion
from app.domain.enums import PlanStatus, PlanVersionState

VERSIONED_FIELDS = (
    "setup_type",
    "structure_stage",
    "structure_low_price",
    "key_support_price",
    "key_resistance_price",
    "reversal_confirmed",
    "structure_invalidated",
    "structure_invalidation_price",
    "structure_invalidation_condition",
    "planned_total_position_pct",
    "initial_entry_price_low",
    "initial_entry_price_high",
    "initial_entry_pct",
    "confirmation_add_enabled",
    "confirmation_trigger_price",
    "confirmation_add_pct",
    "t_reserve_pct",
    "first_target_price",
    "first_target_type",
    "first_target_reduce_pct",
    "remaining_exit_condition",
    "valid_until",
    "user_note",
)


class TradePlanService:
    """Minimal lifecycle service for immutable plan revisions.

    The service does not audit market logic. It only preserves version history and controls
    which already-created version is marked effective.
    """

    @staticmethod
    def create_plan(
        session: Session,
        *,
        instrument_code: str,
        instrument_name: str,
        version_data: Mapping[str, Any],
    ) -> tuple[TradePlan, TradePlanVersion]:
        plan = TradePlan(
            instrument_code=instrument_code,
            instrument_name=instrument_name,
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
            **TradePlanService._clean_version_data(version_data),
        )
        session.add(version)
        session.flush()
        return plan, version

    @staticmethod
    def create_revision(
        session: Session,
        *,
        plan: TradePlan,
        changes: Mapping[str, Any],
        reason: str | None = None,
    ) -> TradePlanVersion:
        current = TradePlanService.get_effective_version(session, plan.id)
        if current is None:
            raise ValueError("当前计划没有有效版本，无法创建修订版本")

        data = {field: getattr(current, field) for field in VERSIONED_FIELDS}
        data.update(TradePlanService._clean_version_data(changes))

        max_version = session.scalar(
            select(func.max(TradePlanVersion.version_number)).where(
                TradePlanVersion.plan_id == plan.id
            )
        )
        revision = TradePlanVersion(
            plan_id=plan.id,
            version_number=(max_version or 0) + 1,
            based_on_version_id=current.id,
            state=PlanVersionState.PENDING_AUDIT,
            is_effective=False,
            version_reason=reason,
            **data,
        )
        session.add(revision)
        session.flush()
        return revision

    @staticmethod
    def activate_version(session: Session, version: TradePlanVersion) -> None:
        current = TradePlanService.get_effective_version(session, version.plan_id)
        if current is not None and current.id != version.id:
            current.is_effective = False
            current.state = PlanVersionState.SUPERSEDED
            # Flush the old effective version first so the partial unique index is never
            # transiently violated while the new version is activated in the same transaction.
            session.flush([current])

        version.is_effective = True
        version.state = PlanVersionState.EFFECTIVE
        session.flush([version])

    @staticmethod
    def get_effective_version(session: Session, plan_id: str) -> TradePlanVersion | None:
        return session.scalar(
            select(TradePlanVersion).where(
                TradePlanVersion.plan_id == plan_id,
                TradePlanVersion.is_effective.is_(True),
            )
        )

    @staticmethod
    def close_plan(session: Session, plan: TradePlan) -> None:
        plan.is_active = False
        plan.status = PlanStatus.CLOSED
        plan.closed_at = utc_now()
        session.flush()

    @staticmethod
    def _clean_version_data(data: Mapping[str, Any]) -> dict[str, Any]:
        unknown = set(data) - set(VERSIONED_FIELDS)
        if unknown:
            joined = ", ".join(sorted(unknown))
            raise ValueError(f"不支持的计划版本字段: {joined}")
        return dict(data)
