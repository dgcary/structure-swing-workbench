"""Account snapshots and the home-page risk overview."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_session
from app.api.schemas import AccountSnapshotRequest
from app.db.models import AccountSnapshot, PositionBucketSnapshot, PositionSnapshot, TradePlan
from app.domain.enums import LabeledEnum
from app.services.trade_plans import TradePlanService

router = APIRouter(tags=["account"])

MAX_RETURNED_SNAPSHOTS = 50

_DISPLAY_QUANT = Decimal("0.0001")


def _enum_dto(member: LabeledEnum | None) -> dict[str, str] | None:
    if member is None:
        return None
    return {"value": member.value, "label": member.label_zh}


def _money(value: Decimal | None) -> str | None:
    """Display formatting only: fixed 4-decimal text, storage values unchanged."""

    if value is None:
        return None
    return format(value.quantize(_DISPLAY_QUANT), "f")


def _time(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _snapshot_dto(snapshot: AccountSnapshot) -> dict[str, Any]:
    return {
        "id": snapshot.id,
        "captured_at": _time(snapshot.captured_at),
        "total_equity": _money(snapshot.total_equity),
        "available_cash": _money(snapshot.available_cash),
        "source": snapshot.source,
        "source_note": snapshot.source_note,
        "positions": [
            {
                "instrument_code": position.instrument_code,
                "instrument_name": position.instrument_name,
                "total_quantity": _money(position.total_quantity),
                "market_value": _money(position.market_value),
                "broker_cost_price": _money(position.broker_cost_price),
                "buckets": [
                    {
                        "bucket_type": _enum_dto(bucket.bucket_type),
                        "quantity": _money(bucket.quantity),
                        "strategy_cost_price": _money(bucket.strategy_cost_price),
                        "effective_cost_price": _money(bucket.effective_cost_price),
                        "realized_t_pnl": _money(bucket.realized_t_pnl),
                    }
                    for bucket in position.buckets
                ],
            }
            for position in snapshot.positions
        ],
    }


def _plan_risk_pct(session: Session, plan: TradePlan) -> str | None:
    """单笔账户风险 = 计划最大亏损 / 账户有效权益；数据不全时返回 None。"""

    version = TradePlanService.get_effective_version(session, plan.id)
    if version is None:
        return None
    entry = version.initial_entry_price_low
    invalidation = version.structure_invalidation_price
    if entry is None or invalidation is None or entry <= 0 or invalidation <= 0:
        return None
    if invalidation >= entry:
        return None
    equity = session.scalar(
        select(AccountSnapshot.total_equity).order_by(
            AccountSnapshot.captured_at.desc(), AccountSnapshot.id.desc()
        )
    )
    if equity is None or equity <= 0:
        return None
    amount = version.planned_total_position_amount
    if amount is None and version.planned_total_position_pct is not None:
        amount = equity * version.planned_total_position_pct / Decimal(100)
    if amount is None or amount <= 0:
        return None
    risk = amount * (entry - invalidation) / entry / equity * Decimal(100)
    return _money(risk.quantize(Decimal("0.0001")))


@router.post("/account/snapshots", status_code=201)
def create_snapshot(
    request: AccountSnapshotRequest, session: Session = Depends(get_session)
) -> dict:
    snapshot = AccountSnapshot(
        captured_at=request.captured_at,
        total_equity=request.total_equity,
        available_cash=request.available_cash,
        source=request.source,
        source_note=request.source_note,
    )
    session.add(snapshot)
    session.flush()
    for item in request.positions:
        position = PositionSnapshot(
            account_snapshot_id=snapshot.id,
            instrument_code=item.instrument_code,
            instrument_name=item.instrument_name,
            total_quantity=item.total_quantity,
            market_value=item.market_value,
            broker_cost_price=item.broker_cost_price,
        )
        session.add(position)
        session.flush()
        for bucket in item.buckets:
            session.add(
                PositionBucketSnapshot(
                    position_snapshot_id=position.id,
                    bucket_type=bucket.bucket_type,
                    quantity=bucket.quantity,
                    strategy_cost_price=bucket.strategy_cost_price,
                    effective_cost_price=bucket.effective_cost_price,
                    realized_t_pnl=bucket.realized_t_pnl,
                )
            )
        session.flush()
    return _snapshot_dto(snapshot)


@router.get("/account/snapshots")
def list_snapshots(
    limit: int = 10, session: Session = Depends(get_session)
) -> list[dict]:
    limit = max(1, min(limit, MAX_RETURNED_SNAPSHOTS))
    snapshots = session.scalars(
        select(AccountSnapshot)
        .options(selectinload(AccountSnapshot.positions).selectinload(PositionSnapshot.buckets))
        .order_by(AccountSnapshot.captured_at.desc(), AccountSnapshot.id.desc())
        .limit(limit)
    )
    return [_snapshot_dto(snapshot) for snapshot in snapshots]


@router.get("/account/overview")
def overview(session: Session = Depends(get_session)) -> dict:
    latest = session.scalar(
        select(AccountSnapshot)
        .options(selectinload(AccountSnapshot.positions).selectinload(PositionSnapshot.buckets))
        .order_by(AccountSnapshot.captured_at.desc(), AccountSnapshot.id.desc())
        .limit(1)
    )
    active_plans = list(
        session.scalars(
            select(TradePlan)
            .where(TradePlan.is_active.is_(True))
            .order_by(TradePlan.created_at.desc(), TradePlan.id.desc())
        )
    )
    plans_payload = []
    for plan in active_plans:
        plans_payload.append(
            {
                "id": plan.id,
                "instrument_code": plan.instrument_code,
                "instrument_name": plan.instrument_name,
                "status": _enum_dto(plan.status),
                "risk_pct": _plan_risk_pct(session, plan),
            }
        )
    risk_values = [
        Decimal(item["risk_pct"]) for item in plans_payload if item["risk_pct"] is not None
    ]
    return {
        "snapshot": _snapshot_dto(latest) if latest else None,
        "active_plans": plans_payload,
        "active_plan_count": len(active_plans),
        "total_risk_pct": _money(sum(risk_values, Decimal(0))) if risk_values else None,
        "position_count": len(latest.positions) if latest else 0,
    }


@router.get("/account/snapshots/{snapshot_id}")
def get_snapshot(snapshot_id: str, session: Session = Depends(get_session)) -> dict:
    snapshot = session.scalar(
        select(AccountSnapshot)
        .where(AccountSnapshot.id == snapshot_id)
        .options(selectinload(AccountSnapshot.positions).selectinload(PositionSnapshot.buckets))
    )
    if snapshot is None:
        raise HTTPException(status_code=404, detail="账户快照不存在")
    return _snapshot_dto(snapshot)
