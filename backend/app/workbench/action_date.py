"""Explicit, opt-in manual date correction for an existing formal action.

Only the intended market date may change. This endpoint never approves an
action, edits an audit, places an order or infers a date from timestamps.
"""
import re
from datetime import UTC, date, datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import TradeAction, TradePlan, TradePlanVersion
from app.domain.enums import ActionStatus, PlanVersionState
from app.workbench.persisted import _observed_at


class ActionDateRequest(BaseModel):
    planned_for_date: date | None
    expected_as_of: datetime

    @field_validator("planned_for_date", mode="before")
    @classmethod
    def strict_explicit_date(cls, value: object) -> object:
        if value is not None and (
            not isinstance(value, str)
            or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None
        ):
            raise ValueError("人工计划日期必须为 YYYY-MM-DD 或 null")
        return value

    @field_validator("expected_as_of")
    @classmethod
    def require_observation_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("原记录时间必须包含时区")
        return value


def update_action_planned_date(
    session: Session, action_id: str, request: ActionDateRequest,
) -> dict[str, object]:
    """Lock, verify and change one PLANNED action; caller owns the transaction."""
    try:
        UUID(action_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="无效的正式动作标识") from exc

    action = session.scalar(
        select(TradeAction).where(TradeAction.id == action_id).with_for_update()
    )
    if action is None:
        raise HTTPException(status_code=404, detail="未找到正式动作")
    if action.status is not ActionStatus.PLANNED:
        raise HTTPException(status_code=409, detail="仅允许修改尚未审计的计划中动作日期")
    version = session.get(TradePlanVersion, action.plan_version_id)
    plan = session.get(TradePlan, version.plan_id) if version is not None else None
    market_today = datetime.now(timezone(timedelta(hours=8))).date()
    if (
        version is None or plan is None or not plan.is_active
        or not version.is_effective
        or version.state not in (
            PlanVersionState.EFFECTIVE, PlanVersionState.EFFECTIVE_WITH_OVERRIDE
        )
        or (version.valid_until is not None and version.valid_until < market_today)
        or _observed_at(version.updated_at) is None
    ):
        raise HTTPException(status_code=409, detail="计划版本无可信的有效状态，禁止修改日期")
    observed = _observed_at(action.updated_at)
    if observed is None:
        raise HTTPException(status_code=409, detail="动作记录时间缺少可信时区或超前")
    # Compare actual instants, not textual UTC offsets. The locked row makes
    # the check-and-update atomic even with simultaneous browser tabs.
    if action.updated_at.astimezone(UTC) != request.expected_as_of.astimezone(UTC):
        raise HTTPException(status_code=409, detail="动作已被更新，请刷新后重试")

    action.planned_for_date = request.planned_for_date
    # onupdate timestamp is set by SQLAlchemy when flushing the changed row.
    session.flush()
    return {
        "saved": True,
        "action_id": action.id,
        "planned_for_date": (
            action.planned_for_date.isoformat() if action.planned_for_date else None
        ),
        "as_of": _observed_at(action.updated_at),
        "trade_execution_enabled": False,
        "notice": "仅更新人工日期；没有生成审计通过或交易许可。",
    }
