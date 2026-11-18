"""Plan lifecycle, version audit and override endpoints."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.schemas import (
    AuditDecisionRequest,
    AuditRunRequest,
    PlanCreateRequest,
    PlanNoteRequest,
    PlanRevisionRequest,
    version_payload,
)
from app.api.serializers import (
    audit_result_dto,
    conflict,
    enum_dto,
    money,
    not_found,
    time_iso,
    version_audits,
)
from app.audit.engine import OverrideContext, apply_override
from app.db.models import (
    AccountSnapshot,
    AuditResult,
    ExecutionFill,
    ManualOverride,
    TradeAction,
    TradePlan,
    TradePlanVersion,
)
from app.domain.enums import PlanStatus
from app.services.plan_audit import PlanVersionFacts, audit_plan_version
from app.services.plan_review import ReviewFill, review_fills
from app.services.trade_plans import TradePlanService

router = APIRouter(tags=["plans"])

ENGINE_VERSION = "m8-plan-rules-v1"


def _get_plan(session: Session, plan_id: str) -> TradePlan:
    plan = session.get(TradePlan, plan_id)
    if plan is None:
        raise not_found("计划不存在")
    return plan


def _get_version(session: Session, version_id: str) -> TradePlanVersion:
    version = session.get(TradePlanVersion, version_id)
    if version is None:
        raise not_found("计划版本不存在")
    return version


def _version_dto(
    session: Session, version: TradePlanVersion, *, with_audits: bool = False
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": version.id,
        "plan_id": version.plan_id,
        "version_number": version.version_number,
        "state": enum_dto(version.state),
        "is_effective": version.is_effective,
        "version_reason": version.version_reason,
        "based_on_version_id": version.based_on_version_id,
        "created_at": time_iso(version.created_at),
        "facts": {
            "setup_type": enum_dto(version.setup_type),
            "structure_stage": enum_dto(version.structure_stage),
            "structure_low_price": money(version.structure_low_price),
            "key_support_price": money(version.key_support_price),
            "key_resistance_price": money(version.key_resistance_price),
            "reversal_confirmed": version.reversal_confirmed,
            "structure_invalidated": version.structure_invalidated,
            "structure_invalidation_price": money(version.structure_invalidation_price),
            "structure_invalidation_condition": version.structure_invalidation_condition,
            "entry_mode": enum_dto(version.entry_mode),
            "planned_total_position_amount": money(version.planned_total_position_amount),
            "planned_total_position_pct": money(version.planned_total_position_pct),
            "initial_entry_price_low": money(version.initial_entry_price_low),
            "initial_entry_price_high": money(version.initial_entry_price_high),
            "initial_entry_pct": money(version.initial_entry_pct),
            "confirmation_add_enabled": version.confirmation_add_enabled,
            "confirmation_trigger_price": money(version.confirmation_trigger_price),
            "confirmation_add_pct": money(version.confirmation_add_pct),
            "t_reserve_pct": money(version.t_reserve_pct),
            "first_target_price": money(version.first_target_price),
            "first_target_type": enum_dto(version.first_target_type),
            "first_target_reduce_pct": money(version.first_target_reduce_pct),
            "remaining_exit_condition": version.remaining_exit_condition,
            "remaining_exit_condition_triggered": version.remaining_exit_condition_triggered,
            "valid_until": version.valid_until.isoformat() if version.valid_until else None,
        },
    }
    if with_audits:
        data["audit_results"] = [audit_result_dto(item) for item in version_audits(session, version.id)]
    return data


def _plan_dto(session: Session, plan: TradePlan, *, with_versions: bool = False) -> dict[str, Any]:
    effective = TradePlanService.get_effective_version(session, plan.id)
    data: dict[str, Any] = {
        "id": plan.id,
        "instrument_code": plan.instrument_code,
        "instrument_name": plan.instrument_name,
        "status": enum_dto(plan.status),
        "is_active": plan.is_active,
        "user_note": plan.user_note,
        "closed_at": time_iso(plan.closed_at),
        "created_at": time_iso(plan.created_at),
        "effective_version_id": effective.id if effective else None,
    }
    if with_versions:
        data["versions"] = [
            _version_dto(session, version, with_audits=True) for version in plan.versions
        ]
    return data


def _latest_equity(session: Session) -> Decimal | None:
    return session.scalar(
        select(AccountSnapshot.total_equity).order_by(
            AccountSnapshot.captured_at.desc(), AccountSnapshot.id.desc()
        )
    )


@router.post("/plans", status_code=201)
def create_plan(request: PlanCreateRequest, session: Session = Depends(get_session)) -> dict:
    try:
        plan, _version = TradePlanService.create_plan(
            session,
            instrument_code=request.instrument_code,
            instrument_name=request.instrument_name,
            version_data=version_payload(request.version),
            user_note=request.user_note,
            account_equity=request.account_equity,
        )
        session.flush()
    except ValueError as exc:
        raise conflict(str(exc)) from exc
    return _plan_dto(session, plan, with_versions=True)


@router.get("/plans")
def list_plans(
    status: PlanStatus | None = None,
    active_only: bool = False,
    session: Session = Depends(get_session),
) -> list[dict]:
    query = select(TradePlan).order_by(TradePlan.created_at.desc(), TradePlan.id.desc())
    if status is not None:
        query = query.where(TradePlan.status == status)
    if active_only:
        query = query.where(TradePlan.is_active.is_(True))
    return [_plan_dto(session, plan) for plan in session.scalars(query)]


@router.get("/plans/{plan_id}")
def get_plan(plan_id: str, session: Session = Depends(get_session)) -> dict:
    plan = _get_plan(session, plan_id)
    return _plan_dto(session, plan, with_versions=True)


@router.patch("/plans/{plan_id}/note")
def update_note(
    plan_id: str, request: PlanNoteRequest, session: Session = Depends(get_session)
) -> dict:
    plan = _get_plan(session, plan_id)
    TradePlanService.update_note(session, plan, request.user_note)
    return _plan_dto(session, plan, with_versions=True)


@router.post("/plans/{plan_id}/revisions", status_code=201)
def create_revision(
    plan_id: str, request: PlanRevisionRequest, session: Session = Depends(get_session)
) -> dict:
    plan = _get_plan(session, plan_id)
    try:
        TradePlanService.create_revision(
            session,
            plan=plan,
            changes=version_payload(request.changes),
            reason=request.reason,
            account_equity=request.account_equity,
        )
        session.flush()
    except ValueError as exc:
        raise conflict(str(exc)) from exc
    return _plan_dto(session, plan, with_versions=True)


@router.post("/plans/{plan_id}/close")
def close_plan(plan_id: str, session: Session = Depends(get_session)) -> dict:
    plan = _get_plan(session, plan_id)
    try:
        TradePlanService.close_plan(session, plan)
        session.flush()
    except ValueError as exc:
        raise conflict(str(exc)) from exc
    return _plan_dto(session, plan, with_versions=True)


@router.post("/plan-versions/{version_id}/submit")
def submit_version(version_id: str, session: Session = Depends(get_session)) -> dict:
    version = _get_version(session, version_id)
    try:
        TradePlanService.submit_for_audit(session, version)
        session.flush()
    except ValueError as exc:
        raise conflict(str(exc)) from exc
    return _version_dto(session, version)


@router.post("/plan-versions/{version_id}/audit")
def run_version_audit(
    version_id: str,
    request: AuditRunRequest,
    session: Session = Depends(get_session),
) -> dict:
    version = _get_version(session, version_id)
    account_equity = (
        request.account_equity if request.account_equity is not None else _latest_equity(session)
    )
    facts = PlanVersionFacts(
        entry_price_low=version.initial_entry_price_low,
        entry_price_high=version.initial_entry_price_high,
        invalidation_price=version.structure_invalidation_price,
        invalidation_condition=version.structure_invalidation_condition,
        initial_entry_pct=version.initial_entry_pct,
        confirmation_add_pct=version.confirmation_add_pct,
        t_reserve_pct=version.t_reserve_pct,
        first_target_reduce_pct=version.first_target_reduce_pct,
        planned_total_position_amount=version.planned_total_position_amount,
        planned_total_position_pct=version.planned_total_position_pct,
    )
    outcome = audit_plan_version(facts, account_equity)
    level = outcome.report.level
    result = AuditResult(
        plan_version_id=version.id,
        level=level,
        summary=(
            f"共 {len(outcome.report.findings)} 条检查结果，"
            f"总体等级：{level.label_zh}；未检查 {len(outcome.skipped)} 条规则"
        ),
        engine_version=ENGINE_VERSION,
        details={
            "findings": [
                {
                    "rule": finding.rule,
                    "level": finding.level.value,
                    "level_zh": finding.level.label_zh,
                    "message": finding.message,
                }
                for finding in outcome.report.findings
            ],
            "skipped_rules": [
                {"rule": item.rule, "reason": item.reason} for item in outcome.skipped
            ],
            "account_equity": money(account_equity),
        },
    )
    session.add(result)
    session.flush()
    return audit_result_dto(result)


@router.post("/plan-versions/{version_id}/decision")
def decide_version(
    version_id: str,
    request: AuditDecisionRequest,
    session: Session = Depends(get_session),
) -> dict:
    version = _get_version(session, version_id)
    result = session.scalar(
        select(AuditResult)
        .where(AuditResult.plan_version_id == version.id)
        .order_by(AuditResult.created_at.desc(), AuditResult.id.desc())
    )
    if result is None:
        raise conflict("该版本还没有审计结果，请先运行审计")

    if not request.approve:
        try:
            TradePlanService.reject_version(session, version)
            session.flush()
        except ValueError as exc:
            raise conflict(str(exc)) from exc
        return {
            "version": _version_dto(session, version),
            "decision": {"allowed": True, "status": "rejected"},
        }

    context = OverrideContext(audit_result_id=result.id, plan_version_id=version.id)
    decision = apply_override(
        result.level,
        context=context,
        user_confirmed=request.user_confirmed,
        reason=request.override_reason,
    )
    status = decision.status
    if not decision.allowed:
        if status.value == "blocked_hard_fail":
            raise conflict("硬性失败不可覆盖，必须修改计划并重新审计")
        raise conflict("可覆盖失败需要用户确认继续，并填写一句覆盖理由")
    with_override = status.value == "approved_with_override"
    try:
        TradePlanService.activate_version(session, version, with_override=with_override)
        session.flush()
    except ValueError as exc:
        raise conflict(str(exc)) from exc
    if with_override:
        session.add(
            ManualOverride(
                audit_result_id=result.id,
                reason=decision.reason or "",
                operator="用户",
            )
        )
        session.flush()
    return {
        "version": _version_dto(session, version),
        "decision": {
            "allowed": decision.allowed,
            "status": status.value,
            "original_level": decision.original_level.value,
            "resulting_level": decision.resulting_level.value,
        },
    }


@router.get("/plans/{plan_id}/review")
def review_plan(plan_id: str, session: Session = Depends(get_session)) -> dict:
    """计划复盘：计划 vs 实际成交汇总，不构成违规判断。"""

    plan = _get_plan(session, plan_id)
    version_ids = [version.id for version in plan.versions]
    action_ids = list(
        session.scalars(
            select(TradeAction.id).where(TradeAction.plan_version_id.in_(version_ids))
        )
    )
    fills = list(
        session.scalars(
            select(ExecutionFill)
            .where(ExecutionFill.action_id.in_(action_ids))
            .order_by(ExecutionFill.executed_at.asc(), ExecutionFill.id.asc())
        )
    )
    effective = TradePlanService.get_effective_version(session, plan.id)
    planned_entry_low = effective.initial_entry_price_low if effective else None
    review = review_fills(
        [
            ReviewFill(fill.side, fill.quantity, fill.price, fill.executed_at)
            for fill in fills
        ],
        planned_entry_low,
    )
    audit_rows = session.execute(
        select(AuditResult.level, func.count())
        .where(
            or_(
                AuditResult.plan_version_id.in_(version_ids),
                AuditResult.action_id.in_(action_ids) if action_ids else False,
            )
        )
        .group_by(AuditResult.level)
    ).all()
    return {
        "plan": {
            "id": plan.id,
            "instrument_code": plan.instrument_code,
            "instrument_name": plan.instrument_name,
            "status": enum_dto(plan.status),
        },
        "review": {
            "total_buy_quantity": money(review.total_buy_quantity),
            "total_sell_quantity": money(review.total_sell_quantity),
            "avg_buy_price": money(review.avg_buy_price),
            "avg_sell_price": money(review.avg_sell_price),
            "remaining_quantity": money(review.remaining_quantity),
            "realized_gross_pnl": money(review.realized_gross_pnl),
            "first_fill_at": time_iso(review.first_fill_at),
            "last_fill_at": time_iso(review.last_fill_at),
            "holding_days": review.holding_days,
            "long_holding_note": review.long_holding_note,
            "entry_deviation_pct": (
                money(review.entry_deviation_pct) if review.entry_deviation_pct is not None else None
            ),
        },
        "audit_summary": [
            {"level": enum_dto(level), "count": count} for level, count in audit_rows
        ],
    }
