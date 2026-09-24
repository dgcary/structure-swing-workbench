from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
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
    "entry_mode",
    "planned_total_position_amount",
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
    "remaining_exit_condition_triggered",
    "valid_until",
)

_POSITION_AMOUNT_FIELD = "planned_total_position_amount"
_POSITION_PCT_FIELD = "planned_total_position_pct"
_MONEY_QUANT = Decimal("0.0001")
_PCT_QUANT = Decimal("0.0001")


class TradePlanService:
    """Lifecycle service for immutable, audit-gated plan revisions.

    This service does not implement M2 discipline rules. It only standardizes plan data,
    preserves history, and controls lifecycle transitions after an external audit decision.
    """

    @staticmethod
    def create_plan(
        session: Session,
        *,
        instrument_code: str,
        instrument_name: str,
        version_data: Mapping[str, Any],
        user_note: str | None = None,
        account_equity: Decimal | None = None,
    ) -> tuple[TradePlan, TradePlanVersion]:
        prepared = TradePlanService._prepare_version_data(
            version_data,
            account_equity=account_equity,
            changed_keys=set(version_data),
        )
        plan = TradePlan(
            instrument_code=instrument_code,
            instrument_name=instrument_name,
            status=PlanStatus.DRAFT,
            is_active=False,
            user_note=user_note,
        )
        session.add(plan)
        session.flush()

        version = TradePlanVersion(
            plan_id=plan.id,
            version_number=1,
            state=PlanVersionState.DRAFT,
            is_effective=False,
            **prepared,
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
        account_equity: Decimal | None = None,
    ) -> TradePlanVersion:
        current = TradePlanService.get_effective_version(session, plan.id)
        if current is None:
            raise ValueError("当前计划没有生效版本，无法创建修订版本")

        clean_changes = TradePlanService._clean_version_data(changes)
        data = {field: getattr(current, field) for field in VERSIONED_FIELDS}
        data.update(clean_changes)
        data = TradePlanService._normalize_position_size(
            data,
            account_equity=account_equity,
            changed_keys=set(clean_changes),
        )

        max_version = session.scalar(
            select(func.max(TradePlanVersion.version_number)).where(
                TradePlanVersion.plan_id == plan.id
            )
        )
        revision = TradePlanVersion(
            plan_id=plan.id,
            version_number=(max_version or 0) + 1,
            based_on_version_id=current.id,
            state=PlanVersionState.DRAFT,
            is_effective=False,
            version_reason=reason,
            **data,
        )
        session.add(revision)
        session.flush()
        return revision

    @staticmethod
    def submit_for_audit(session: Session, version: TradePlanVersion) -> None:
        if version.state is not PlanVersionState.DRAFT:
            raise ValueError("只有草稿版本可以提交审计")
        version.state = PlanVersionState.PENDING_AUDIT
        session.flush([version])

    @staticmethod
    def activate_version(
        session: Session,
        version: TradePlanVersion,
        *,
        with_override: bool = False,
    ) -> None:
        if version.state is not PlanVersionState.PENDING_AUDIT:
            raise ValueError("只有待审计版本可以进入生效状态")

        plan = session.get(TradePlan, version.plan_id)
        if plan is None:
            raise ValueError("计划不存在")

        # A draft plan only becomes the active main plan after an audit outcome allows activation.
        plan.status = PlanStatus.ACTIVE
        plan.is_active = True
        plan.closed_at = None
        session.flush([plan])

        current = TradePlanService.get_effective_version(session, version.plan_id)
        if current is not None and current.id != version.id:
            current.is_effective = False
            current.state = PlanVersionState.SUPERSEDED
            session.flush([current])

        version.is_effective = True
        version.state = (
            PlanVersionState.EFFECTIVE_WITH_OVERRIDE
            if with_override
            else PlanVersionState.EFFECTIVE
        )
        session.flush([version])

    @staticmethod
    def reject_version(session: Session, version: TradePlanVersion) -> None:
        if version.state is not PlanVersionState.PENDING_AUDIT:
            raise ValueError("只有待审计版本可以标记为已拒绝")
        version.is_effective = False
        version.state = PlanVersionState.REJECTED
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
    def update_note(session: Session, plan: TradePlan, user_note: str | None) -> None:
        """Update non-critical metadata without creating a new auditable plan version."""

        plan.user_note = user_note
        session.flush([plan])

    @staticmethod
    def close_plan(session: Session, plan: TradePlan) -> None:
        current = TradePlanService.get_effective_version(session, plan.id)
        if current is None:
            current = session.scalar(
                select(TradePlanVersion)
                .where(TradePlanVersion.plan_id == plan.id)
                .order_by(TradePlanVersion.version_number.desc())
                .limit(1)
            )

        if current is not None and current.state not in {
            PlanVersionState.REJECTED,
            PlanVersionState.SUPERSEDED,
            PlanVersionState.CLOSED,
        }:
            current.is_effective = False
            current.state = PlanVersionState.CLOSED
            session.flush([current])

        plan.is_active = False
        plan.status = PlanStatus.CLOSED
        plan.closed_at = utc_now()
        session.flush([plan])

    @staticmethod
    def _prepare_version_data(
        data: Mapping[str, Any],
        *,
        account_equity: Decimal | None,
        changed_keys: set[str],
    ) -> dict[str, Any]:
        clean = TradePlanService._clean_version_data(data)
        return TradePlanService._normalize_position_size(
            clean,
            account_equity=account_equity,
            changed_keys=changed_keys,
        )

    @staticmethod
    def _normalize_position_size(
        data: Mapping[str, Any],
        *,
        account_equity: Decimal | None,
        changed_keys: set[str],
    ) -> dict[str, Any]:
        normalized = dict(data)
        amount = normalized.get(_POSITION_AMOUNT_FIELD)
        pct = normalized.get(_POSITION_PCT_FIELD)

        if amount is None and pct is None:
            return normalized

        amount_changed = _POSITION_AMOUNT_FIELD in changed_keys
        pct_changed = _POSITION_PCT_FIELD in changed_keys

        if amount is not None and pct is not None and not (amount_changed ^ pct_changed):
            return normalized

        if account_equity is None:
            if amount is None or pct is None:
                raise ValueError("仅填写计划总仓位金额或比例时，必须提供账户总权益用于换算")
            return normalized
        if account_equity <= 0:
            raise ValueError("账户总权益必须大于0")

        if pct_changed and not amount_changed:
            normalized[_POSITION_AMOUNT_FIELD] = (
                account_equity * pct / Decimal(100)
            ).quantize(_MONEY_QUANT)
        elif amount_changed and not pct_changed:
            normalized[_POSITION_PCT_FIELD] = (
                amount / account_equity * Decimal(100)
            ).quantize(_PCT_QUANT)
        elif amount is None:
            normalized[_POSITION_AMOUNT_FIELD] = (
                account_equity * pct / Decimal(100)
            ).quantize(_MONEY_QUANT)
        elif pct is None:
            normalized[_POSITION_PCT_FIELD] = (
                amount / account_equity * Decimal(100)
            ).quantize(_PCT_QUANT)

        return normalized

    @staticmethod
    def _clean_version_data(data: Mapping[str, Any]) -> dict[str, Any]:
        unknown = set(data) - set(VERSIONED_FIELDS)
        if unknown:
            joined = ", ".join(sorted(unknown))
            raise ValueError(f"不支持的计划版本字段: {joined}")
        return dict(data)
