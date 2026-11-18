"""Execution actions and fill recording endpoints."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_session
from app.api.schemas import ActionCreateRequest, FillCreateRequest
from app.api.serializers import (
    action_audits,
    action_dto,
    audit_result_dto,
    conflict,
    enum_dto,
    money,
    not_found,
    time_iso,
)
from app.db.models import (
    AuditResult,
    ExecutionFill,
    ManualOverride,
    TradeAction,
    TradePlan,
    TradePlanVersion,
)
from app.domain.enums import ActionStatus, AuditLevel
from app.services.action_audit import (
    ActionFacts,
    VersionFacts,
    audit_planned_action,
    audit_recorded_fill,
    blocked_by_hard_fail,
    expected_side,
)
from app.services.t_cycle_view import (
    MAX_COMPLETED_CYCLES_PER_DAY,
    T_CYCLE_ACTION_TYPES,
    CycleFill,
    summarize_cycle,
)

router = APIRouter(tags=["actions"])

ENGINE_VERSION = "m9-action-rules-v1"

_EXECUTABLE_STATES = {
    ActionStatus.PLANNED,
    ActionStatus.AUDITED,
    ActionStatus.EXECUTING,
    ActionStatus.PARTIALLY_FILLED,
}


def _get_version(session: Session, version_id: str) -> TradePlanVersion:
    version = session.get(TradePlanVersion, version_id)
    if version is None:
        raise not_found("计划版本不存在")
    return version


def _get_action(session: Session, action_id: str) -> TradeAction:
    action = session.get(TradeAction, action_id)
    if action is None:
        raise not_found("交易动作不存在")
    return action


def _version_facts(version: TradePlanVersion) -> VersionFacts:
    return VersionFacts(
        entry_mode=version.entry_mode,
        version_entry_low=version.initial_entry_price_low,
        version_entry_high=version.initial_entry_price_high,
        reversal_confirmed=version.reversal_confirmed,
        confirmation_trigger_price=version.confirmation_trigger_price,
        structure_invalidated=version.structure_invalidated,
    )


def _action_facts(action: TradeAction) -> ActionFacts:
    return ActionFacts(
        action_type=action.action_type,
        side=action.side,
        planned_price_low=action.planned_price_low,
        planned_price_high=action.planned_price_high,
        t_cycle_key=action.t_cycle_key,
    )


def _store_audit(
    session: Session,
    *,
    action: TradeAction,
    level: AuditLevel,
    summary: str,
    details: dict[str, Any],
) -> AuditResult:
    result = AuditResult(
        action_id=action.id,
        level=level,
        summary=summary,
        engine_version=ENGINE_VERSION,
        details=details,
    )
    session.add(result)
    session.flush()
    return result


def _outcome_details(
    outcome: Any, *, extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {
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
    }
    if extra:
        payload.update(extra)
    return payload


@router.get("/t-cycles")
def list_t_cycles(
    instrument_code: str | None = None,
    session: Session = Depends(get_session),
) -> list[dict]:
    """T 循环分组视图：按 (证券, t_cycle_key) 汇总成交，提示每日循环上限。"""

    query = (
        select(TradeAction)
        .join(TradePlanVersion, TradeAction.plan_version_id == TradePlanVersion.id)
        .join(TradePlan, TradePlanVersion.plan_id == TradePlan.id)
        .options(selectinload(TradeAction.plan_version))
        .where(TradeAction.t_cycle_key.is_not(None))
        .where(TradeAction.action_type.in_(tuple(T_CYCLE_ACTION_TYPES)))
        .order_by(TradeAction.created_at.asc(), TradeAction.id.asc())
    )
    if instrument_code:
        query = query.where(TradePlan.instrument_code == instrument_code)
    grouped: dict[tuple[str, str], list[TradeAction]] = {}
    for action in session.scalars(query):
        plan = session.get(TradePlan, action.plan_version.plan_id)
        if plan is None:
            continue
        grouped.setdefault((plan.instrument_code, action.t_cycle_key or ""), []).append(action)

    completed_days: dict[tuple[str, Any], int] = {}
    payload: list[dict] = []
    for (code, cycle_key), cycle_actions in grouped.items():
        action_ids = [action.id for action in cycle_actions]
        fills = list(
            session.scalars(
                select(ExecutionFill)
                .where(ExecutionFill.action_id.in_(action_ids))
                .order_by(ExecutionFill.executed_at.asc(), ExecutionFill.id.asc())
            )
        )
        summary = summarize_cycle(
            [CycleFill(fill.side, fill.quantity, fill.price) for fill in fills]
        )
        plan = session.get(TradePlan, cycle_actions[0].plan_version.plan_id)
        day = fills[0].executed_at.date() if fills else cycle_actions[0].created_at.date()
        if summary.completed:
            key = (code, day)
            completed_days[key] = completed_days.get(key, 0) + 1
        payload.append(
            {
                "t_cycle_key": cycle_key,
                "instrument_code": code,
                "instrument_name": plan.instrument_name if plan else code,
                "day": day.isoformat(),
                "status": "已完成" if summary.completed else "进行中",
                "matched_quantity": money(summary.matched_quantity),
                "matched_gross_pnl": money(summary.matched_gross_pnl),
                "remaining_quantity": money(summary.remaining_quantity),
                "open_side": enum_dto(summary.open_side),
                "fill_count": len(fills),
                "action_ids": action_ids,
            }
        )
    for item in payload:
        key = (item["instrument_code"], date.fromisoformat(item["day"]))
        item["exceeds_daily_limit"] = completed_days.get(key, 0) > MAX_COMPLETED_CYCLES_PER_DAY
    return payload


@router.post("/plan-versions/{version_id}/actions", status_code=201)
def create_action(
    version_id: str, request: ActionCreateRequest, session: Session = Depends(get_session)
) -> dict:
    version = _get_version(session, version_id)
    if not version.is_effective:
        raise conflict("执行动作只能挂在生效的计划版本上")
    expected = expected_side(request.action_type)
    if request.side is not expected:
        raise conflict(
            f"动作方向与类型不一致：{request.action_type.label_zh}应为「{expected.label_zh}」"
        )
    if request.planned_price_low is not None and request.planned_price_low <= 0:
        raise conflict("计划价格必须大于0")
    action = TradeAction(
        plan_version_id=version.id,
        action_type=request.action_type,
        side=request.side,
        status=ActionStatus.PLANNED,
        planned_price_low=request.planned_price_low,
        planned_price_high=request.planned_price_high,
        planned_quantity=request.planned_quantity,
        planned_position_pct=request.planned_position_pct,
        t_cycle_key=request.t_cycle_key,
        user_note=request.user_note,
    )
    session.add(action)
    session.flush()
    return action_dto(session, action)


@router.get("/actions")
def list_actions(
    status: ActionStatus | None = None,
    session: Session = Depends(get_session),
) -> list[dict]:
    """Read + filter listing for the workbench."""

    query = (
        select(TradeAction)
        .options(selectinload(TradeAction.plan_version))
        .order_by(TradeAction.created_at.desc(), TradeAction.id.desc())
    )
    if status is not None:
        query = query.where(TradeAction.status == status)
    return [action_dto(session, action) for action in session.scalars(query)]


@router.get("/actions/{action_id}")
def get_action(action_id: str, session: Session = Depends(get_session)) -> dict:
    action = _get_action(session, action_id)
    payload = action_dto(session, action)
    payload["audit_results"] = [
        audit_result_dto(item) for item in action_audits(session, action.id)
    ]
    return payload


@router.post("/actions/{action_id}/audit")
def audit_action(action_id: str, session: Session = Depends(get_session)) -> dict:
    action = _get_action(session, action_id)
    version = session.get(TradePlanVersion, action.plan_version_id)
    assert version is not None
    outcome = audit_planned_action(_version_facts(version), _action_facts(action))
    level = outcome.report.level
    result = _store_audit(
        session,
        action=action,
        level=level,
        summary=(
            f"共 {len(outcome.report.findings)} 条检查结果，"
            f"总体等级：{level.label_zh}；未检查 {len(outcome.skipped)} 条规则"
        ),
        details=_outcome_details(outcome),
    )
    if action.status is ActionStatus.PLANNED and level is not AuditLevel.HARD_FAIL:
        action.status = ActionStatus.AUDITED
        session.flush()
    return audit_result_dto(result)


@router.post("/actions/{action_id}/fills", status_code=201)
def record_fill(
    action_id: str, request: FillCreateRequest, session: Session = Depends(get_session)
) -> dict:
    action = _get_action(session, action_id)
    if action.status not in _EXECUTABLE_STATES:
        raise conflict(f"动作当前状态为「{action.status.label_zh}」，不能录入成交")
    if request.side is not None and request.side is not action.side:
        raise conflict(f"成交方向「{request.side.label_zh}」与动作方向「{action.side.label_zh}」不一致")
    if request.quantity <= 0:
        raise conflict("成交数量必须大于0")
    if request.price <= 0:
        raise conflict("成交价格必须大于0")

    version = session.get(TradePlanVersion, action.plan_version_id)
    assert version is not None
    outcome = audit_recorded_fill(
        _version_facts(version),
        _action_facts(action),
        fill_price=request.price,
        fill_quantity=request.quantity,
    )
    if blocked_by_hard_fail(outcome):
        raise conflict("成交触发硬性失败（结构失效后扩大风险或成交严重越界），已拒绝录入")

    level = outcome.report.level
    override_reason = (request.override_reason or "").strip()
    if level is AuditLevel.OVERRIDABLE_FAIL and not (
        request.override_confirmed and override_reason
    ):
        raise conflict("成交越界构成可覆盖失败：需要用户确认继续，并填写一句覆盖理由")

    fill = ExecutionFill(
        action_id=action.id,
        side=action.side,
        quantity=request.quantity,
        price=request.price,
        fee=request.fee,
        executed_at=request.executed_at,
        source=request.source,
        external_execution_id=request.external_execution_id,
    )
    session.add(fill)
    result = _store_audit(
        session,
        action=action,
        level=outcome.report.level,
        summary=(
            f"成交 {request.quantity} @ {money(request.price)}；"
            f"共 {len(outcome.report.findings)} 条检查结果，总体等级：{outcome.report.level.label_zh}"
        ),
        details=_outcome_details(
            outcome,
            extra={
                "fill": {
                    "quantity": money(request.quantity),
                    "price": money(request.price),
                    "executed_at": time_iso(request.executed_at),
                    "source": request.source,
                }
            },
        ),
    )
    if level is AuditLevel.OVERRIDABLE_FAIL:
        session.add(
            ManualOverride(
                audit_result_id=result.id,
                reason=override_reason,
                operator="用户",
            )
        )

    _update_action_status(session, action, request.quantity)
    session.flush()
    return {"action": action_dto(session, action), "audit_result": audit_result_dto(result)}


def _update_action_status(
    session: Session, action: TradeAction, fill_quantity: Decimal
) -> None:
    if action.status not in {
        ActionStatus.PLANNED,
        ActionStatus.AUDITED,
        ActionStatus.EXECUTING,
        ActionStatus.PARTIALLY_FILLED,
    }:
        return
    if action.planned_quantity is None:
        action.status = ActionStatus.EXECUTING
        session.flush()
        return
    total = session.scalar(
        select(func.coalesce(func.sum(ExecutionFill.quantity), 0)).where(
            ExecutionFill.action_id == action.id
        )
    )
    if total >= action.planned_quantity:
        action.status = ActionStatus.FILLED
    else:
        action.status = ActionStatus.PARTIALLY_FILLED
    session.flush()


@router.patch("/actions/{action_id}/cancel")
def cancel_action(action_id: str, session: Session = Depends(get_session)) -> dict:
    action = _get_action(session, action_id)
    if action.status not in {ActionStatus.PLANNED, ActionStatus.AUDITED}:
        raise conflict(f"动作当前状态为「{action.status.label_zh}」，不能取消")
    action.status = ActionStatus.CANCELLED
    session.flush()
    return action_dto(session, action)
