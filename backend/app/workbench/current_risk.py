"""Fail-closed §15.64 current-risk arithmetic; no market-data authentication here.

This pure calculator deliberately does not read quotes or broker positions.
Callers must independently verify price currency, stop provenance, complete
holdings and account equity before using any calculated amount in the UI.
No result is a trading instruction, permission or account-level risk gate.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True)
class PositionRiskFacts:
    symbol: str
    current_price: Decimal | None
    price_source: str | None
    price_as_of: datetime | None
    price_current_verified: bool
    core_quantity: Decimal | None
    core_stop: Decimal | None
    t_quantity: Decimal | None
    t_stop: Decimal | None


@dataclass(frozen=True)
class RiskResult:
    status: Literal["available", "unavailable", "crossed"]
    amount: Decimal | None
    percent: Decimal | None
    core_amount: Decimal | None
    t_amount: Decimal | None
    warning: str


def _valid_positive(value: Decimal | None) -> bool:
    return isinstance(value, Decimal) and value.is_finite() and value > 0


def _valid_quantity(value: Decimal | None) -> bool:
    return isinstance(value, Decimal) and value.is_finite() and value >= 0


def _observed(source: str | None, at: datetime | None, now: datetime) -> bool:
    return (
        isinstance(source, str) and bool(source.strip())
        and isinstance(at, datetime) and at.tzinfo is not None
        and at.utcoffset() is not None and at.astimezone(UTC) <= now
    )


def _unavailable(reason: str) -> RiskResult:
    return RiskResult("unavailable", None, None, None, None, reason)


def position_current_risk(
    facts: PositionRiskFacts, *, now: datetime | None = None,
) -> RiskResult:
    """Compute remaining CORE/T downside only from separately trusted facts.

    The T stop is mandatory whenever a T bucket has a positive quantity.
    A crossed stop is a review condition, never a negative risk or zero.
    """
    current = now or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        return _unavailable("当前时间缺少时区，无法核算当前风险。")
    current = current.astimezone(UTC)
    if (not facts.price_current_verified
            or not _observed(facts.price_source, facts.price_as_of, current)
            or not _valid_positive(facts.current_price)):
        return _unavailable("缺少已独立核实的当前市价、来源或有效时间。")
    if (not _valid_quantity(facts.core_quantity)
            or not _valid_quantity(facts.t_quantity)
            or facts.core_quantity + facts.t_quantity <= 0):
        return _unavailable("核心仓或T仓数量缺失、异常，或没有可核算的持仓。")
    buckets = (
        (facts.core_quantity, facts.core_stop, "核心仓"),
        (facts.t_quantity, facts.t_stop, "T仓"),
    )
    for quantity, stop, label in buckets:
        if quantity > 0 and not _valid_positive(stop):
            return _unavailable(f"{label}缺少独立有效的结构失效价或止损价。")
    if any(
        quantity > 0 and facts.current_price < stop
        for quantity, stop, _ in buckets
    ):
        return RiskResult(
            "crossed", None, None, None, None,
            "当前市价已穿越核心仓或T仓有效失效价；须人工确认计划状态，不能生成负风险。",
        )
    core = (
        (facts.current_price - facts.core_stop) * facts.core_quantity
        if facts.core_quantity > 0 else Decimal(0)
    )
    t = (
        (facts.current_price - facts.t_stop) * facts.t_quantity
        if facts.t_quantity > 0 else Decimal(0)
    )
    return RiskResult(
        "available", core + t, None, core, t,
        "仅为已核实输入的当前剩余下行风险计算，不代表交易许可。",
    )


def account_current_risk(
    positions: list[PositionRiskFacts],
    *, equity: Decimal | None, equity_source: str | None,
    equity_as_of: datetime | None, equity_verified: bool,
    complete_holdings: bool, now: datetime | None = None,
) -> RiskResult:
    """Sum current downside; no independent account-level 3% hard threshold.

    A partial inventory or one untrusted CORE/T bucket must not be
    promoted into a seemingly complete account-risk number.
    """
    current = now or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        return _unavailable("当前时间缺少时区，无法核算账户风险。")
    current = current.astimezone(UTC)
    if (not equity_verified or not complete_holdings or not positions
            or not _valid_positive(equity)
            or not _observed(equity_source, equity_as_of, current)):
        return _unavailable("缺少可信账户权益或完整持仓，账户当前总风险不可用。")
    symbols = [position.symbol for position in positions]
    if (any(not symbol or not symbol.strip() for symbol in symbols)
            or len(symbols) != len(set(symbols))):
        return _unavailable("持仓证券标识缺失或重复，账户风险不可用。")
    parts = [position_current_risk(position, now=current) for position in positions]
    if any(part.status == "unavailable" for part in parts):
        return _unavailable("至少一笔持仓缺少可信当前市价或CORE/T独立止损。")
    if any(part.status == "crossed" for part in parts):
        return RiskResult(
            "crossed", None, None, None, None,
            "至少一笔持仓已穿越有效失效价；账户当前风险不可用，须人工复核。",
        )
    total = sum((part.amount for part in parts if part.amount is not None), Decimal(0))
    return RiskResult(
        "available", total, total / equity * Decimal(100), None, None,
        "账户当前风险仅展示，不新增账户级总风险硬门槛，也不授权交易。",
    )
