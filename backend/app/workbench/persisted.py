"""Source-labelled, read-only projections of persisted M1 account and plan records.

This module never authorizes a trade or treats local drafts as effective plans.
A database row is not proof of a live broker connection.
"""

import re
from collections import Counter
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal, localcontext

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AccountSnapshot,
    AuditResult,
    ExecutionFill,
    PositionBucketSnapshot,
    PositionSnapshot,
    TradeAction,
    TradePlan,
    TradePlanVersion,
)
from app.domain.enums import (
    ActionStatus,
    ActionType,
    AuditLevel,
    OrderSide,
    PlanVersionState,
    PositionBucketType,
)
from app.workbench.t_cycle_evidence import project_recorded_t_cycles


def _observed_at(value: datetime | None) -> str | None:
    """Do not invent a timezone for a database value without one."""
    if value is None or value.tzinfo is None or value.utcoffset() is None:
        return None
    # Future-dated database rows are not observed facts. Allow only small
    # clock skew; never let an incorrect timestamp authenticate account data.
    if value.astimezone(UTC) > datetime.now(UTC) + timedelta(minutes=5):
        return None
    return value.isoformat()


def _number(value: Decimal | None) -> str | None:
    return str(value) if value is not None and value.is_finite() else None


def _fact(value: Decimal | int | str | None, source: str, at: str | None) -> dict | None:
    if value is None or at is None:
        return None
    return {"value": str(value), "source": source, "as_of": at}


def _core_only_risk(quantity: Decimal, cost: Decimal | None, stop: Decimal | None) -> Decimal | None:
    """Historical CORE downside only; T inventory requires its own verified stop."""
    if (
        not quantity.is_finite() or quantity <= 0
        or cost is None or not cost.is_finite()
        or stop is None or not stop.is_finite()
        or stop <= 0 or cost <= stop
    ):
        return None
    # M1 NUMERIC(20,4) quantity × NUMERIC(18,4) price can carry up to
    # 38 significant digits. Default Decimal precision (28) silently rounds
    # a historical risk fact before the UI displays it as sourced evidence.
    with localcontext() as context:
        context.prec = 64
        return quantity * (cost - stop)



def _recorded_plan_holding_matches_snapshot(
    session: Session, plan: TradePlan, snapshot_at: datetime, snapshot_qty: Decimal,
) -> bool:
    """Conservative §15.43 attribution; a same-symbol holding is not plan ownership.

    Compare all recorded fills from every version of this plan, not just its
    first buy. A complete exit, partial/unknown inventory, conflicting fills,
    or fills from another plan for this symbol cannot keep an expired entry
    plan on the *effective* list. This is still NOT broker certification.
    """
    if not snapshot_qty.is_finite() or snapshot_qty <= 0:
        return False
    rows = list(session.execute(
        select(ExecutionFill, TradeAction)
        .join(TradeAction, ExecutionFill.action_id == TradeAction.id)
        .join(TradePlanVersion, TradeAction.plan_version_id == TradePlanVersion.id)
        .where(
            TradePlanVersion.plan_id == plan.id,
            ExecutionFill.executed_at <= snapshot_at,
        )
    ))
    if not rows:
        return False
    saw_initial_buy = False
    with localcontext() as context:
        context.prec = 64
        net = Decimal(0)
        for fill, action in rows:
            if (
                fill.side != action.side
                or not fill.quantity.is_finite() or fill.quantity <= 0
                or not fill.price.is_finite() or fill.price <= 0
                or not fill.fee.is_finite() or fill.fee < 0
                or not isinstance(fill.source, str) or not fill.source.strip()
                or _observed_at(fill.executed_at) is None
            ):
                return False
            if action.action_type == ActionType.INITIAL_ENTRY:
                if action.side != OrderSide.BUY:
                    return False
                saw_initial_buy = True
            net += fill.quantity if fill.side == OrderSide.BUY else -fill.quantity
            # A recorded sell cannot dispose of more of this plan than it owns.
            if net < 0:
                return False
    if not saw_initial_buy or net <= 0 or net != snapshot_qty:
        return False
    # Even equal quantities cannot attribute the latest snapshot to this plan
    # when another plan for the same instrument has recorded transactions.
    other_plan_fill = session.scalar(
        select(ExecutionFill.id)
        .join(TradeAction, ExecutionFill.action_id == TradeAction.id)
        .join(TradePlanVersion, TradeAction.plan_version_id == TradePlanVersion.id)
        .join(TradePlan, TradePlanVersion.plan_id == TradePlan.id)
        .where(
            TradePlan.instrument_code == plan.instrument_code,
            TradePlan.id != plan.id,
            ExecutionFill.executed_at <= snapshot_at,
        ).limit(1)
    )
    return other_plan_fill is None


def project_persisted(session: Session) -> dict[str, object]:
    """Read only existing records; no migrations, writes or synthetic data."""
    snapshot = session.scalar(
        select(AccountSnapshot).order_by(
            AccountSnapshot.captured_at.desc(), AccountSnapshot.id.desc()
        ).limit(1)
    )
    metrics: dict[str, dict] = {}
    holdings: list[dict] | None = None
    # Risk is never inferred from broker display cost or an unverified T stop.
    risk_inventory: dict[str, tuple[Decimal, Decimal]] = {}
    positive_snapshot_quantities: dict[str, Decimal] = {}
    snapshot_at: datetime | None = None
    snapshot_source = ""
    if snapshot is not None:
        at = _observed_at(snapshot.captured_at)
        # A database row without a non-blank origin is not traceable evidence.
        # Do not turn an empty source into a seemingly valid labelled fact.
        source_name = snapshot.source.strip() if isinstance(snapshot.source, str) else ""
        if not source_name:
            at = None
        source = f"账户快照/{source_name}/{snapshot.id}" if source_name else ""
        snapshot_at = snapshot.captured_at if at is not None else None
        snapshot_source = source
        for key, value in (
            ("equity", snapshot.total_equity),
            ("available_cash", snapshot.available_cash),
        ):
            fact = _fact(
                _number(value) if value.is_finite() and value >= 0 else None,
                source, at,
            )
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
            valid = all(row.total_quantity.is_finite() and row.total_quantity >= 0
                        for row in positions)
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
                    set(allocations) == {PositionBucketType.CORE, PositionBucketType.T} and
                    all(value.is_finite() and value >= 0
                        for value in allocations.values()) and
                    position.total_quantity.is_finite() and
                    sum(allocations.values(), Decimal(0)) == position.total_quantity
                )
                if not consistent:
                    core = t_qty = None
                    # Conflicting bucket quantities cannot support a risk estimate.
                # An exact CORE/T split is necessary but insufficient for risk:
                # any T quantity requires a separate T stop absent from M1 snapshots.
                if position.total_quantity.is_finite() and position.total_quantity > 0:
                    core_bucket = next(
                        (row for row in buckets
                         if row.bucket_type is PositionBucketType.CORE), None
                    )
                    core_cost = (
                        core_bucket.strategy_cost_price if core_bucket is not None else None
                    )
                    if (
                        consistent and t_qty == 0 and core == position.total_quantity
                        and core_cost is not None and core_cost.is_finite() and core_cost > 0
                    ):
                        risk_inventory[position.instrument_code] = (core, core_cost)
                conflict = (
                    not position.total_quantity.is_finite()
                    or position.total_quantity < 0
                )
                holdings.append({
                    "symbol": position.instrument_code,
                    "status": "conflict" if conflict else (
                        "snapshot" if _number(position.broker_cost_price) is not None else "partial"
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
                positive_snapshot_quantities = {
                    row.instrument_code: row.total_quantity
                    for row in positions if row.total_quantity > 0
                }
                metrics["position_count"] = _fact(
                    sum(row.total_quantity > 0 for row in positions), source, at
                )
                if (
                    snapshot.total_equity.is_finite() and snapshot.total_equity > 0 and
                    all(row.market_value is not None and row.market_value.is_finite()
                        and row.market_value >= 0
                        for row in positions)
                ):
                    # M1 NUMERIC amounts may exceed the default 28-digit
                    # Decimal context when summed and divided by equity.
                    with localcontext() as context:
                        context.prec = 64
                        exposure = sum((row.market_value for row in positions), Decimal(0))
                        ratio = exposure * Decimal(100) / snapshot.total_equity
                    # Do not hide overexposure. Section 15.48 requires the
                    # actual gross position ratio to remain visible even when
                    # it exceeds the default 100% limit. This is a labelled
                    # snapshot fact, NOT a broker-verified execution audit.
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
    # Before initial entry, an expired entry deadline excludes the plan.
    # After a recorded initial buy with a positive holding, §15.43 preserves
    # the main plan; neither historical fact grants execution permission.
    # Use the A-share market calendar date, not the server's UTC date.
    market_today = datetime.now(timezone(timedelta(hours=8))).date()
    eligible_versions = []
    held_after_entry_versions: set[str] = set()
    for version, plan in versions:
        valid_until = getattr(version, "valid_until", None)
        if valid_until is not None and valid_until < market_today:
            # §15.43: valid_until is an entry deadline, not an automatic
            # expiry for a plan with an already executed initial buy and
            # a still-positive holding. Require BOTH recorded entry evidence
            # and a dated position snapshot; neither alone proves ownership.
            if (snapshot_at is None or
                    positive_snapshot_quantities.get(plan.instrument_code, Decimal(0)) <= 0):
                continue
            if not _recorded_plan_holding_matches_snapshot(
                session, plan, snapshot_at,
                positive_snapshot_quantities[plan.instrument_code],
            ):
                continue
            held_after_entry_versions.add(version.id)
        # Future-dated versions cannot certify effective plans; timezone-naive
        # legacy records remain display-only, never risk-authenticating facts.
        updated_at = version.updated_at
        if (
            updated_at is not None and updated_at.tzinfo is not None
            and updated_at.utcoffset() is not None
            and _observed_at(updated_at) is None
        ):
            continue
        eligible_versions.append((version, plan))
    # Multiple independently effective plans for one symbol have no unique
    # stop-loss assignment to the broker's aggregate position snapshot.
    # Do not pick an arbitrary first plan and certify a partial risk total.
    effective_plan_counts = Counter(plan.instrument_code for _, plan in eligible_versions)
    for version, plan in eligible_versions:
        source = f"正式计划版本/{version.id}"
        historical_cost_risk_estimate = None
        # Historical strategy cost is not a current market quote. Keep the
        # estimate separate from initial/current risk (Notion section 15.64).
        # Compare two dated facts, never apply a newer plan to an older snapshot.
        if (
            snapshot_at is not None and _observed_at(version.updated_at) is not None
            and version.updated_at <= snapshot_at
            and plan.instrument_code in risk_inventory
            and effective_plan_counts[plan.instrument_code] == 1
        ):
            quantity, cost = risk_inventory[plan.instrument_code]
            historical_cost_risk_estimate = _core_only_risk(
                quantity, cost, version.structure_invalidation_price
            )
        plans.append({
            "id": version.id, "symbol": plan.instrument_code,
            "name": plan.instrument_name,
            "version": version.version_number,
            "state_zh": version.state.label_zh,
            "invalidation_price": _number(version.structure_invalidation_price),
            "first_target_price": _number(version.first_target_price),
            "initial_risk": None, "current_risk": None,
            "historical_cost_risk_estimate": _number(historical_cost_risk_estimate),
            "source": source + (
                f" + {snapshot_source}/核心仓"
                if historical_cost_risk_estimate is not None else ""
            ),
            "as_of": _observed_at(version.updated_at),
            "warning": (
                "历史策略成本至现有失效价的估算（元），非经核验初始风险；"
                "缺可信当前市价及完整CORE/T仓事实，当前风险不可用，不构成交易许可。"
                if historical_cost_risk_estimate is not None else
                "同一证券存在多份有效计划，无法唯一对应持仓止损；风险未核验，不授权交易。"
                if effective_plan_counts[plan.instrument_code] > 1 else
                "已记录首次买入且历史快照记录持仓；入场有效期不再自动终止主计划。"
                "本地成交与持仓未获券商认证，风险及最新审计仍须核验。"
                if version.id in held_after_entry_versions else
                "仅为已存储的计划状态；风险来源不足，未验证完整账户及最新审计。"
            ),
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
            # An action dated in the future is not a recorded current fact.
            # Keep timezone-naive legacy rows display-only, but reject
            # explicitly future-dated rows rather than showing them as pending.
            action_time = action.updated_at
            if (
                action_time is not None and action_time.tzinfo is not None
                and action_time.utcoffset() is not None
                and _observed_at(action_time) is None
            ):
                continue
            # An update timestamp is not an intended execution date.
            # Only an explicit date with a trustworthy record timestamp can
            # be labelled as today's manual plan, never as trading permission.
            action_observed = _observed_at(action.updated_at)
            planned_for_date = getattr(action, "planned_for_date", None)
            if action_observed is None:
                planned_for_date = None
            date_status = (
                "today" if planned_for_date == market_today else
                "other_day" if planned_for_date is not None else "unverified"
            )
            actions.append({
                "id": action.id, "symbol": plan.instrument_code,
                "action_zh": action.action_type.label_zh,
                "status_zh": action.status.label_zh,
                "planned_price_low": _number(action.planned_price_low),
                "planned_price_high": _number(action.planned_price_high),
                "source": f"正式交易动作/{action.id}",
                "as_of": action_observed,
                "planned_for_date": (
                    planned_for_date.isoformat() if planned_for_date is not None else None
                ),
                "date_status": date_status,
                "executable": False,
                "warning": (
                    "人工计划日期已记录；仍需实时审计与券商核对，不构成交易许可。"
                    if planned_for_date is not None else
                    "未核验人工计划执行日期；仅展示历史动作，不能认定为今日待办。"
                ),
            })
            audit_rows.extend(session.scalars(
                select(AuditResult).where(AuditResult.action_id == action.id)
            ))
        audit_rows.extend(session.scalars(
            select(AuditResult).where(AuditResult.plan_version_id == version.id)
        ))

    # No independently verified, timestamped market quote or complete CORE/T
    # stop inventory is available in M1 snapshots. Never publish a historical
    # cost-based estimate as the live account-risk percentage.

    audits = []
    for row in sorted(audit_rows, key=lambda item: (item.created_at, item.id)):
        # Future-dated audit records must not appear as completed historical
        # checks, nor influence the highest audit severity metric.
        if (
            row.created_at is not None and row.created_at.tzinfo is not None
            and row.created_at.utcoffset() is not None
            and _observed_at(row.created_at) is None
        ):
            continue
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
        # Recorded T legs are partial evidence, not a broker-complete daily count.
        "t_cycle_evidence": project_recorded_t_cycles(session, market_today),
    }
