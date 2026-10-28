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
from app.workbench.account_snapshot_preview import _market_session_status

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
    a wrong side, invalid quantity/price, missing source/time or a closing leg
    before its opening leg, or a fill dated in the future, is never a completed T.
    """
    current = now or datetime.now(UTC)
    # Third-party calendar data may reject known closures, but can never
    # authenticate an official session or the completeness of broker fills.
    market_session_status = _market_session_status(market_day)
    # A user-entered cycle key is not globally unique. Never pair legs from
    # different plan versions, even if their symbol and key happen to match.
    # Keep missing keys structurally separate from user-entered strings.
    grouped: dict[
        tuple[str, str | None, str | None, str | None],
        list[tuple[ActionType, ExecutionFill]],
    ] = defaultdict(list)
    # Broker execution references are source-scoped, not cycle-scoped. A
    # repeated reference across different actions or plan versions is still
    # conflicting evidence; counting both could certify a fictitious T cycle.
    seen_fill_ids: set[str] = set()
    duplicate_fill_ids: set[str] = set()
    seen_external_ids: set[tuple[str, str]] = set()
    duplicate_external_ids: set[tuple[str, str]] = set()
    for _, _, action_type, fill in records:
        # Reconcile execution identities across *all* recorded actions.
        # A broker reference reused by an ordinary trade can invalidate a
        # T leg just as surely as one reused by a different T cycle.
        fill_id = str(fill.id)
        if fill_id in seen_fill_ids:
            duplicate_fill_ids.add(fill_id)
        seen_fill_ids.add(fill_id)
        source = getattr(fill, "source", None)
        external_id = getattr(fill, "external_execution_id", None)
        if (isinstance(source, str) and source.strip()
                and isinstance(external_id, str) and external_id.strip()):
            reference = (source.strip(), external_id.strip())
            if reference in seen_external_ids:
                duplicate_external_ids.add(reference)
            seen_external_ids.add(reference)
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
                    or stamp.astimezone(UTC) > current.astimezone(UTC)):
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
        conflict = (
            invalid_time or dates != {market_day} or key is None
            or market_session_status != "session"
        )
        for action_type, fill in legs:
            direction, leg, side = T_LEGS[action_type]
            directions.add(direction)
            stamp = fill.executed_at
            source = getattr(fill, "source", None)
            external_id = getattr(fill, "external_execution_id", None)
            if str(fill.id) in duplicate_fill_ids:
                conflict = True
            if (isinstance(source, str) and source.strip()
                    and isinstance(external_id, str) and external_id.strip()
                    and (source.strip(), external_id.strip()) in duplicate_external_ids):
                conflict = True
            # PostgreSQL NUMERIC may contain NaN; never add a non-finite
            # quantity to the running balance (Decimal comparisons can raise).
            valid_quantity = (
                isinstance(fill.quantity, Decimal)
                and fill.quantity.is_finite()
                and fill.quantity > 0
            )
            # A recorded fill with an absent, zero or non-finite execution
            # price cannot certify a completed cycle, even if legs balance.
            valid_price = (
                isinstance(getattr(fill, "price", None), Decimal)
                and fill.price.is_finite()
                and fill.price > 0
            )
            # Fees are recorded execution facts, not optional plan values.
            # A non-finite, negative or absent fee makes the pair unsuitable
            # as a coherent recorded T cycle, even when prices/quantities match.
            fee = getattr(fill, "fee", None)
            valid_fee = (
                isinstance(fee, Decimal)
                and fee.is_finite()
                and fee >= 0
            )
            if (
                fill.side != side or not valid_quantity or not valid_price
                or not valid_fee
                or not isinstance(source, str) or not source.strip()
            ):
                conflict = True
            sources.append(f"成交记录/{fill.id}/{source}")
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
        ordered_timeline = sorted(timeline, key=lambda item: item[0])
        for index, (stamp, leg, quantity) in enumerate(ordered_timeline):
            if (previous_stamp == stamp and previous_leg is not None
                    and previous_leg != leg):
                conflict = True  # Same-timestamp legs have no reliable ordering.
            balance += quantity if leg == "open" else -quantity
            if balance < 0:
                conflict = True
            # A completed balance followed by another leg under the same
            # cycle key represents a second trading decision, not a split
            # fill of the original cycle. Do not merge multiple round trips
            # into one apparently valid T cycle and hide the daily limit.
            if balance == 0 and index < len(ordered_timeline) - 1:
                conflict = True
            previous_stamp, previous_leg = stamp, leg
        state = "conflict" if conflict else "closed" if opening == closing else "open"
        dated = [
            fill.executed_at for _, fill in legs
            if fill.executed_at is not None and fill.executed_at.tzinfo is not None
            and fill.executed_at.utcoffset() is not None
        ]
        # End-of-day classification is a *review hint*, not a persisted
        # BROKEN_T_CYCLE or a broker-reconciled position change. The residual
        # first-leg quantity must be checked against the full broker ledger
        # and the main plan before it can become an ordinary add/reduction.
        market_now = current.astimezone(MARKET_TZ)
        session_ended = (
            market_day < market_now.date()
            or (market_day == market_now.date()
                and (market_now.hour, market_now.minute) >= (15, 0))
        )
        unclosed_at_day_end = state == "open" and session_ended
        residual = opening - closing if unclosed_at_day_end else None
        ordinary_effect = (
            "普通减仓待核验" if unclosed_at_day_end and "positive" in directions else
            "普通加仓待核验" if unclosed_at_day_end and "reverse" in directions else None
        )
        result.append({
            "end_of_day_unclosed": unclosed_at_day_end,
            "residual_quantity": str(residual) if residual is not None else None,
            "ordinary_effect": ordinary_effect,
            "requires_reaudit": unclosed_at_day_end,
            "symbol": symbol,
            "cycle_key": key,
            "plan_version_id": plan_version_id,
            "market_date": market_day.isoformat(),
            "market_calendar_status": market_session_status,
            "direction": next(iter(directions)) if len(directions) == 1 else None,
            "state": state,
            "opening_quantity": str(opening) if not conflict else None,
            "closing_quantity": str(closing) if not conflict else None,
            "as_of": max(dated).isoformat() if dated and not invalid_time else None,
            "sources": sorted(sources),
            "broker_reconciled": False,
            "trade_execution_enabled": False,
            "warning": (
                "成交方向、价格、费用、数量、日期、来源或重复成交编号冲突；不可用于T次数核验。"
                if conflict else
                "已过当日收盘且记录中仍有未闭环T；剩余第一腿仅提示待核验的普通加减仓，"
                "必须核对券商全量成交、主计划与风险后重新审计；未自动转仓或授权交易。"
                if unclosed_at_day_end else
                "仅为数据库中已记录成交的单周期证据；未验证券商成交完整性、"
                "日内总T次数及T+1可卖数量，不授权交易。"
            ),
        })
    # The broker ledger is incomplete, so fewer than three recorded cycles
    # cannot establish compliance. Three *distinct, internally consistent*
    # closed cycles do establish a lower-bound warning for the same symbol/day,
    # even across plan versions. Never promote this to a verified daily count.
    recorded_closed_by_symbol: dict[str, int] = defaultdict(int)
    for cycle in result:
        if cycle["state"] == "closed":
            recorded_closed_by_symbol[str(cycle["symbol"])] += 1
    for cycle in result:
        over_limit = recorded_closed_by_symbol[str(cycle["symbol"])] > 2
        # null means "not proven from incomplete records", NOT "rule passed".
        cycle["recorded_daily_limit_alert"] = True if over_limit else None
        if over_limit:
            cycle["warning"] = (
                "该证券本交易日已记录至少3个独立完整T配对，疑似超过单票单日最多2次；"
                "券商全量成交尚未对账，必须人工复核，不授权交易。"
                + str(cycle["warning"])
            )
    return result


def project_recorded_t_cycles(session: Session, market_day: date) -> list[dict[str, object]]:
    """Query recorded execution fills only; drafts and unfilled actions are not facts."""
    # Include non-T actions for source-scoped duplicate execution detection;
    # recorded_t_cycles groups and displays only the T legs themselves.
    fills = session.scalars(select(ExecutionFill).join(
        TradeAction, ExecutionFill.action_id == TradeAction.id
    ))
    records = [
        (fill.action.plan_version.plan.instrument_code, fill.action.t_cycle_key,
         fill.action.action_type, fill)
        for fill in fills
    ]
    return recorded_t_cycles(records, market_day)
