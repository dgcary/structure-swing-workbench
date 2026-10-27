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

from app.db.models import ExecutionFill, TradeAction, TradePlan, TradePlanVersion
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
    grouped: dict[tuple[str, str | None], list[tuple[ActionType, ExecutionFill]]] = (
        defaultdict(list)
    )
    for symbol, key, action_type, fill in records:
        if action_type in T_LEGS:
            # Do not combine unrelated unkeyed fills into a fictitious cycle.
            group_key = key.strip() if key and key.strip() else None
            grouped[(symbol, group_key if group_key else f"unkeyed:{fill.id}")] .append(
                (action_type, fill)
            )
    result = []
    for (symbol, key), legs in sorted(grouped.items()):
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
        conflict = invalid_time or dates != {market_day} or key.startswith("unkeyed:")
        for action_type, fill in legs:
            direction, leg, side = T_LEGS[action_type]
            directions.add(direction)
            stamp = fill.executed_at
            if (fill.side != side or not fill.quantity.is_finite()
                    or fill.quantity <= 0 or not fill.source.strip()):
                conflict = True
            sources.append(f"成交记录/{fill.id}/{fill.source}")
            if leg == "open":
                opening += fill.quantity
                if stamp.tzinfo is not None and stamp.utcoffset() is not None:
                    first_open = min(first_open, stamp) if first_open else stamp
            else:
                closing += fill.quantity
                if stamp.tzinfo is not None and stamp.utcoffset() is not None:
                    first_close = min(first_close, stamp) if first_close else stamp
        if (len(directions) != 1 or opening <= 0 or closing > opening
                or (first_close is not None and
                    (first_open is None or first_close < first_open))):
            conflict = True
        state = "conflict" if conflict else "closed" if opening == closing else "open"
        dated = [
            fill.executed_at for _, fill in legs
            if fill.executed_at is not None and fill.executed_at.tzinfo is not None
            and fill.executed_at.utcoffset() is not None
        ]
        result.append({
            "symbol": symbol,
            "cycle_key": None if key.startswith("unkeyed:") else key,
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
    rows = session.execute(
        select(TradePlan.instrument_code, TradeAction.t_cycle_key,
               TradeAction.action_type, ExecutionFill)
        .join(TradePlanVersion, TradeAction.plan_version_id == TradePlanVersion.id)
        .join(TradePlan, TradePlanVersion.plan_id == TradePlan.id)
        .join(ExecutionFill, ExecutionFill.action_id == TradeAction.id)
        .where(TradeAction.action_type.in_(list(T_LEGS)))
    )
    return recorded_t_cycles(list(rows), market_day)
