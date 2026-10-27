"""Source-labelled, read-only projections of persisted M1 account and plan records.

This module never authorizes a trade or treats local drafts as effective plans.
A database row is not proof of a live broker connection.
"""

from datetime import datetime
from decimal import Decimal
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AccountSnapshot, AuditResult, PositionBucketSnapshot, PositionSnapshot,
    TradeAction, TradePlan, TradePlanVersion,
)
from app.domain.enums import ActionStatus, AuditLevel, PlanVersionState, PositionBucketType


def _observed_at(value: datetime | None) -> str | None:
    """Do not invent a timezone for a database value without one."""
    if value is None or value.tzinfo is None or value.utcoffset() is None:
        return None
    return value.isoformat()


def _number(value: Decimal | None) -> str | None:
    return str(value) if value is not None and value.is_finite() else None


def _fact(value: Decimal | int | str | None, source: str, at: str | None) -> dict | None:
    if value is None or at is None:
        return None
    return {"value": str(value), "source": source, "as_of": at}


def project_persisted(session: Session) -> dict[str, object]:
    """Read only existing records; no migrations, writes or synthetic data."""
    snapshot = session.scalar(
        select(AccountSnapshot).order_by(
            AccountSnapshot.captured_at.desc(), AccountSnapshot.id.desc()
        ).limit(1)
    )
    metrics: dict[str, dict] = {}
    holdings: list[dict] | None = None
    if snapshot is not None:
        at = _observed_at(snapshot.captured_at)
        source = f"账户快照/{snapshot.source}/{snapshot.id}"
        for key, value in (
            ("equity", snapshot.total_equity),
            ("available_cash", snapshot.available_cash),
        ):
            fact = _fact(_number(value), source, at)
            if fact is not None:
                metrics[key] = fact
        positions = list(session.scalars(
            select(PositionSnapshot).where(
                PositionSnapshot.account_snapshot_id == snapshot.id
            ).order_by(PositionSnapshot.instrument_code)
        ))
        # A timestamp without timezone or an unrecognized symbol is not display-grade evidence.
        if positions and at is not None and all(
            re.fullmatch(r"(?:\d{6}(?:\.(?:SH|SZ|BJ))?|(?:SH|SZ|BJ)\d{6})",
                         row.instrument_code) for row in positions
        ):
            holdings = []
            valid = all(row.total_quantity >= 0 for row in positions)
            for position in positions:
                buckets = list(session.scalars(
                    select(PositionBucketSnapshot).where(
                        PositionBucketSnapshot.position_snapshot_id == position.id
                    )
                ))
                allocations = {row.bucket_type: row.quantity for row in buckets}
                core = allocations.get(PositionBucketType.CORE)
                t_qty = allocations.get(PositionBucketType.T)
                consistent = (
                    len(allocations) == len(buckets) and
                    all(value >= 0 for value in allocations.values()) and
                    sum(allocations.values(), Decimal(0)) <= position.total_quantity
                )
                if not consistent:
                    core = t_qty = None
                conflict = position.total_quantity < 0
                holdings.append({
                    "symbol": position.instrument_code,
                    "status": "conflict" if conflict else (
                        "snapshot" if position.broker_cost_price is not None else "partial"
                    ),
                    "quantity": None if conflict else _number(position.total_quantity),
                    "broker_display_cost": (
                        None if conflict else _number(position.broker_cost_price)
                    ),
                    "core_quantity": None if conflict else _number(core),
                    "t_quantity": None if conflict else _number(t_qty),
                    "source": source, "as_of": at,
                    "warning": (
                        "持仓数量冲突，禁止据此计算仓位。" if conflict else
                        "核心/T仓分配冲突，未予采信。" if not consistent else
                        "历史快照非实时；核心/T仓与可卖数量不能等同，T+1须另行核验。"
                    ),
                    "applied_fill_ids": [],
                    "unanchored_fill_delta": None,
                })
            if valid and at is not None:
                metrics["position_count"] = _fact(
                    sum(row.total_quantity > 0 for row in positions), source, at
                )
                if (
                    snapshot.total_equity > 0 and
                    all(row.market_value is not None and row.market_value >= 0
                        for row in positions)
                ):
                    exposure = sum((row.market_value for row in positions), Decimal(0))
                    ratio = exposure * Decimal(100) / snapshot.total_equity
                    if ratio <= 100:
                        metrics["position_ratio"] = _fact(
                            ratio, source + "/持仓市值", at
                        )

    versions = list(session.execute(
        select(TradePlanVersion, TradePlan)
        .join(TradePlan, TradePlanVersion.plan_id == TradePlan.id)
        .where(
            TradePlan.is_active.is_(True),
            TradePlanVersion.is_effective.is_(True),
            TradePlanVersion.state.in_([
                PlanVersionState.EFFECTIVE, PlanVersionState.EFFECTIVE_WITH_OVERRIDE
            ]),
        )
        .order_by(TradePlan.instrument_code)
    ))
    plans = []
    actions = []
    audit_rows = []
    for version, plan in versions:
        source = f"正式计划版本/{version.id}"
        plans.append({
            "id": version.id, "symbol": plan.instrument_code,
            "name": plan.instrument_name,
            "version": version.version_number,
            "state_zh": version.state.label_zh,
            "invalidation_price": _number(version.structure_invalidation_price),
            "first_target_price": _number(version.first_target_price),
            "initial_risk": None, "current_risk": None,
            "source": source, "as_of": _observed_at(version.updated_at),
            "warning": "仅为已存储的计划状态；未验证完整账户及最新审计，不构成交易许可。",
        })
        for action in session.scalars(
            select(TradeAction).where(
                TradeAction.plan_version_id == version.id,
                TradeAction.status.in_([
                    ActionStatus.PLANNED, ActionStatus.AUDITED,
                    ActionStatus.EXECUTING, ActionStatus.PARTIALLY_FILLED,
                ]),
            )
        ):
            actions.append({
                "id": action.id, "symbol": plan.instrument_code,
                "action_zh": action.action_type.label_zh,
                "status_zh": action.status.label_zh,
                "planned_price_low": _number(action.planned_price_low),
                "planned_price_high": _number(action.planned_price_high),
                "source": f"正式交易动作/{action.id}",
                "as_of": _observed_at(action.updated_at),
                "executable": False,
                "warning": "仅展示人工记录；未执行实时审计与券商核对。",
            })
            audit_rows.extend(session.scalars(
                select(AuditResult).where(AuditResult.action_id == action.id)
            ))
        audit_rows.extend(session.scalars(
            select(AuditResult).where(AuditResult.plan_version_id == version.id)
        ))

    audits = []
    for row in sorted(audit_rows, key=lambda item: (item.created_at, item.id)):
        audits.append({
            "id": row.id,
            "level": row.level.value,
            "level_zh": row.level.label_zh,
            "summary": row.summary,
            "source": f"审计记录/{row.id}/{row.engine_version}",
            "as_of": _observed_at(row.created_at),
            "executable": False,
            "warning": "历史审计记录仅供查阅；不能替代当前动作的完整审计。",
        })
    severity = {
        AuditLevel.PASS.value: 0,
        AuditLevel.WARNING.value: 1,
        AuditLevel.OVERRIDABLE_FAIL.value: 2,
        AuditLevel.HARD_FAIL.value: 3,
    }
    dated = [row for row in audits if row["as_of"] is not None]
    if dated:
        worst = max(dated, key=lambda item: severity[item["level"]])
        metrics["highest_audit"] = {
            "value": worst["level_zh"], "source": worst["source"],
            "as_of": worst["as_of"],
        }
    return {
        "metrics": metrics,
        "holdings": holdings,
        "effective_plans": plans,
        "pending_actions": actions,
        "audit_results": audits,
    }
