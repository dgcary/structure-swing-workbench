"""Shared DTO serializers for the workbench API layer."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import AuditResult, ManualOverride, TradeAction, TradePlan
from app.domain.enums import LabeledEnum

DISPLAY_QUANT = Decimal("0.0001")


def enum_dto(member: LabeledEnum | None) -> dict[str, str] | None:
    if member is None:
        return None
    return {"value": member.value, "label": member.label_zh}


def money(value: Decimal | None) -> str | None:
    """Display formatting only: fixed 4-decimal text, storage values unchanged."""

    if value is None:
        return None
    return format(value.quantize(DISPLAY_QUANT), "f")


def time_iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=404, detail=detail)


def conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=409, detail=detail)


def override_dto(item: ManualOverride) -> dict[str, Any]:
    return {
        "id": item.id,
        "reason": item.reason,
        "operator": item.operator,
        "created_at": time_iso(item.created_at),
        "revoked_at": time_iso(item.revoked_at),
    }


def audit_result_dto(result: AuditResult) -> dict[str, Any]:
    return {
        "id": result.id,
        "level": enum_dto(result.level),
        "summary": result.summary,
        "engine_version": result.engine_version,
        "details": result.details,
        "overrides": [override_dto(item) for item in result.overrides],
        "created_at": time_iso(result.created_at),
    }


def action_dto(session: Session, action: TradeAction) -> dict[str, Any]:
    version = action.plan_version
    plan = session.get(TradePlan, version.plan_id)
    return {
        "id": action.id,
        "action_type": enum_dto(action.action_type),
        "side": enum_dto(action.side),
        "status": enum_dto(action.status),
        "planned_price_low": money(action.planned_price_low),
        "planned_price_high": money(action.planned_price_high),
        "planned_quantity": money(action.planned_quantity),
        "planned_position_pct": money(action.planned_position_pct),
        "t_cycle_key": action.t_cycle_key,
        "user_note": action.user_note,
        "created_at": time_iso(action.created_at),
        "plan_version_id": version.id,
        "version_number": version.version_number,
        "plan": {
            "id": version.plan_id,
            "instrument_code": plan.instrument_code,
            "instrument_name": plan.instrument_name,
        }
        if plan
        else None,
    }


def version_audits(session: Session, version_id: str) -> list[AuditResult]:
    return list(
        session.scalars(
            select(AuditResult)
            .where(AuditResult.plan_version_id == version_id)
            .options(selectinload(AuditResult.overrides))
            .order_by(AuditResult.created_at.desc(), AuditResult.id.desc())
        )
    )


def action_audits(session: Session, action_id: str) -> list[AuditResult]:
    return list(
        session.scalars(
            select(AuditResult)
            .where(AuditResult.action_id == action_id)
            .options(selectinload(AuditResult.overrides))
            .order_by(AuditResult.created_at.desc(), AuditResult.id.desc())
        )
    )
