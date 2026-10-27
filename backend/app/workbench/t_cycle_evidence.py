"""Read-only M8 evidence for recorded T legs; never infer a broker-complete daily count.

M1 stores action-level T cycle keys and execution fills, but has no broker
completeness watermark or verified T+1 settlement ledger. This projection
therefore reports only individual recorded cycles and keeps the dashboard's
total daily T metrics unavailable until completeness can be established.
"""

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ExecutionFill, TradeAction
from app.domain.enums import ActionType, OrderSide

MARKET_TZ = timezone(timedelta(hours=8))
T_LEGS = {
    ActionType.POSITIVE_T_SELL: ("positive", "open", OrderSide.SELL),
    ActionType.POSITIVE_T_BUYBACK: ("positive", "close", OrderSide.BUY),
    ActionType.REVERSE_T_BUY: ("reverse", "open", OrderSide.BUY),
    ActionType.REVERSE_T_SELL: ("reverse", "close", OrderSide.SELL),
}


def recorded_t_cycles(
    records: list[tuple[str, str | None, ActionType, ExecutionFill]],
    market_day: date,
    *,
    now: datetime | None = None,
) -> list[dict[str, object]]:
    """Reconcile fill legs per plan-independent symbol/key without guessing fills.

    An unkeyed T fill is explicitly conflicting. A key reused across days,
    a wrong side, non-finite quantity, missing source/time or a closing leg
    before its opening leg is never a completed T.
    """
    current = now or datetime.now(UTC)
    # A user-entered cycle key is not globally unique. Never pair legs from
    # different plan versions, even if their symbol and key happen to match.
    # Keep missing keys structurally separate from user-entered strings.
    grouped: dict[
        tuple[str, str | None, str | None, str | None],
        list[tuple[ActionType, ExecutionFill]],
    ] = defaultdict(list)
    for symbol, key, action_type, fill in records:
        if action_type in T_LEGS:
            group_key = key.strip() if key and key.strip() else None
            action = getattr(fill, "action", None)
            plan_version_id = getattr(action, "plan_version_id", None)
            grouped[(
                symbol, plan_version_id, group_key,
                str(fill.id) if group_key is None else None,
            )].append((action_type, fill))
    result = []
    for (symbol, plan_version_id, key, _), legs in sorted(
        grouped.items(), key=lambda item: tuple(part or "" for part in item[0])
    ):
        dates = set()
        invalid_time = False
        for _, fill in legs:
            stamp = fill.executed_at
            if (stamp is None or stamp.tzinfo is None or stamp.utcoffset() is None
                    or stamp.astimezone(UTC) > current + timedelta(minutes=5)):
                invalid_time = True
            else:
                dates.add(stamp.astimezone(MARKET_TZ).date())
        if market_day not in dates:
            continue
        opening = closing = Decimal(0)
        first_open: datetime | None = None
        first_close: datetime | None = None
        directions = set()
        sources = []
        timeline: list[tuple[datetime, str, Decimal]] = []
        conflict = invalid_time or dates != {market_day} or key is None
        for action_type, fill in legs:
            direction, leg, side = T_LEGS[action_type]
            directions.add(direction)
            stamp = fill.executed_at
            # PostgreSQL NUMERIC may contain NaN; never add a non-finite
            # quantity to the running balance (Decimal comparisons can raise).
            valid_quantity = (
                isinstance(fill.quantity, Decimal)
                and fill.quantity.is_finite()
                and fill.quantity > 0
            )
            if fill.side != side or not valid_quantity or not fill.source or not fill.source.strip():
                conflict = True
            sources.append(f"成交记录/{fill.id}/{fill.source}")
            if not valid_quantity:
                continue
            if stamp is not None and stamp.tzinfo is not None and stamp.utcoffset() is not None:
                timeline.append((stamp, leg, fill.quantity))
            if leg == "open":
                opening += fill.quantity
                if stamp is not None and stamp.tzinfo is not None and stamp.utcoffset() is not None:
                    first_open = min(first_open, stamp) if first_open else stamp
            else:
                closing += fill.quantity
                if stamp is not None and stamp.tzinfo is not None and stamp.utcoffset() is not None:
                    first_close = min(first_close, stamp) if first_close else stamp
        if (len(directions) != 1 or opening <= 0 or closing > opening
                or (first_close is not None and
                    (first_open is None or first_close < first_open))):
            conflict = True
        # A later opening fill cannot retroactively cover an earlier closing
        # fill, even if aggregate buy/sell quantities eventually match.
        balance = Decimal(0)
        previous_stamp: datetime | None = None
        previous_leg: str | None = None
        for stamp, leg, quantity in sorted(timeline, key=lambda item: item[0]):
            if (previous_stamp == stamp and previous_leg is not None
                    and previous_leg != leg):
                conflict = True  # Same-timestamp legs have no reliable ordering.
            balance += quantity if leg == "open" else -quantity
            if balance < 0:
                conflict = True
            previous_stamp, previous_leg = stamp, leg
        state = "conflict" if conflict else "closed" if opening == closing else "open"
        dated = [
            fill.executed_at for _, fill in legs
            if fill.executed_at is not None and fill.executed_at.tzinfo is not None
            and fill.executed_at.utcoffset() is not None
        ]
        result.append({
            "symbol": symbol,
            "cycle_key": key,
            "plan_version_id": plan_version_id,
            "market_date": market_day.isoformat(),
            "direction": next(iter(directions)) if len(directions) == 1 else None,
            "state": state,
            "opening_quantity": str(opening) if not conflict else None,
            "closing_quantity": str(closing) if not conflict else None,
            "as_of": max(dated).isoformat() if dated and not invalid_time else None,
            "sources": sorted(sources),
            "broker_reconciled": False,
            "trade_execution_enabled": False,
            "warning": (
                "成交方向、数量、日期或来源冲突；不可用于T次数核验。"
                if conflict else
                "仅为数据库中已记录成交的单周期证据；未验证券商成交完整性、"
                "日内总T次数及T+1可卖数量，不授权交易。"
            ),
        })
    return result


def project_recorded_t_cycles(session: Session, market_day: date) -> list[dict[str, object]]:
    """Query recorded execution fills only; drafts and unfilled actions are not facts."""
    fills = session.scalars(
        select(ExecutionFill).join(TradeAction, ExecutionFill.action_id == TradeAction.id)
        .where(TradeAction.action_type.in_(list(T_LEGS)))
    )
    records = [
        (fill.action.plan_version.plan.instrument_code, fill.action.t_cycle_key,
         fill.action.action_type, fill)
        for fill in fills
    ]
    return recorded_t_cycles(records, market_day)
