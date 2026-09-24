from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import IntEnum
from typing import Iterable

from app.domain.enums import ActionType, AuditLevel, EntryMode, OrderSide

DEFAULT_ONE_WAY_SLIPPAGE = Decimal("0.002")


class Severity(IntEnum):
    PASS = 0
    WARNING = 1
    OVERRIDABLE_FAIL = 2
    HARD_FAIL = 3


_LEVEL_SEVERITY = {
    AuditLevel.PASS: Severity.PASS,
    AuditLevel.WARNING: Severity.WARNING,
    AuditLevel.OVERRIDABLE_FAIL: Severity.OVERRIDABLE_FAIL,
    AuditLevel.HARD_FAIL: Severity.HARD_FAIL,
}


@dataclass(frozen=True, slots=True)
class AuditFinding:
    rule: str
    level: AuditLevel
    message: str


@dataclass(frozen=True, slots=True)
class AuditReport:
    level: AuditLevel
    findings: tuple[AuditFinding, ...]


@dataclass(frozen=True, slots=True)
class OverrideDecision:
    allowed: bool
    resulting_level: AuditLevel
    reason: str | None = None


def _finding(rule: str, level: AuditLevel, message: str) -> AuditFinding:
    return AuditFinding(rule=rule, level=level, message=message)


def aggregate(findings: Iterable[AuditFinding]) -> AuditReport:
    items = tuple(findings)
    if not items:
        return AuditReport(AuditLevel.PASS, ())
    level = max((item.level for item in items), key=_LEVEL_SEVERITY.__getitem__)
    return AuditReport(level, items)


def audit_single_trade_risk(risk_pct: Decimal) -> AuditFinding:
    if risk_pct <= Decimal("2"):
        return _finding("single_trade_risk", AuditLevel.PASS, "单笔账户风险不超过2%")
    if risk_pct <= Decimal("3"):
        return _finding("single_trade_risk", AuditLevel.WARNING, "单笔账户风险高于2%且不超过3%")
    return _finding("single_trade_risk", AuditLevel.HARD_FAIL, "单笔账户风险高于3%")


def audit_position_split(
    *, initial_pct: Decimal, confirmation_pct: Decimal, t_reserve_pct: Decimal
) -> tuple[AuditFinding, ...]:
    specs = (
        ("initial_position", initial_pct, Decimal("35"), Decimal("45"), "初始建仓"),
        ("confirmation_position", confirmation_pct, Decimal("25"), Decimal("35"), "确认加仓"),
        ("t_reserve_position", t_reserve_pct, Decimal("25"), Decimal("35"), "T仓/机动仓"),
    )
    return tuple(
        _finding(
            rule,
            AuditLevel.PASS if low <= value <= high else AuditLevel.WARNING,
            f"{label}比例{'在' if low <= value <= high else '不在'}通过范围内",
        )
        for rule, value, low, high, label in specs
    )


def audit_initial_entry(
    *,
    mode: EntryMode,
    execution_price: Decimal,
    planned_price_low: Decimal,
    planned_price_high: Decimal | None = None,
) -> AuditFinding:
    if mode is EntryMode.SINGLE_PRICE:
        if execution_price <= planned_price_low:
            return _finding("initial_entry", AuditLevel.PASS, "初始建仓未向上追过计划价")
        return _finding("initial_entry", AuditLevel.HARD_FAIL, "初始建仓高于单一计划买入价")

    if planned_price_high is None:
        raise ValueError("价格区间模式必须提供区间上沿")
    if execution_price > planned_price_high:
        return _finding("initial_entry", AuditLevel.HARD_FAIL, "初始建仓高于计划区间上沿")
    lower_limit = planned_price_low * Decimal("0.98")
    if execution_price < lower_limit:
        return _finding("initial_entry", AuditLevel.HARD_FAIL, "低于计划区间下沿超过2%，需要新计划版本")
    return _finding("initial_entry", AuditLevel.PASS, "初始建仓价格位于原计划允许边界内")


def audit_confirmation_add(
    *, reversal_confirmed: bool, execution_price: Decimal, trigger_price: Decimal
) -> AuditFinding:
    if not reversal_confirmed:
        return _finding("confirmation_add", AuditLevel.HARD_FAIL, "用户尚未确认反转成立")
    if execution_price < trigger_price:
        return _finding("confirmation_add", AuditLevel.HARD_FAIL, "成交发生在确认加仓触发价之前")
    if execution_price > trigger_price * Decimal("1.03"):
        return _finding("confirmation_add", AuditLevel.HARD_FAIL, "确认加仓成交价超过触发价3%上限")
    return _finding("confirmation_add", AuditLevel.PASS, "确认加仓满足触发与价格范围")


def audit_target_one(*, reduce_pct: Decimal, reached: bool, completed: bool) -> tuple[AuditFinding, ...]:
    ratio_level = AuditLevel.PASS if Decimal("40") <= reduce_pct <= Decimal("60") else AuditLevel.WARNING
    findings = [
        _finding("target_one_reduce_pct", ratio_level, "第一目标减仓比例范围检查")
    ]
    if reached and not completed:
        findings.append(_finding("target_one_completion", AuditLevel.WARNING, "已达到第一目标但计划减仓尚未完成"))
    else:
        findings.append(_finding("target_one_completion", AuditLevel.PASS, "第一目标减仓完成状态无警告"))
    return tuple(findings)


_RISK_INCREASING_ACTIONS = {
    ActionType.INITIAL_ENTRY,
    ActionType.CONFIRMATION_ADD,
    ActionType.ORDINARY_ADD,
    ActionType.REVERSE_T_BUY,
    ActionType.POSITIVE_T_SELL,
}


def audit_structure_invalidation(*, invalidated: bool, action_type: ActionType) -> AuditFinding:
    if invalidated and action_type in _RISK_INCREASING_ACTIONS:
        return _finding("structure_invalidation", AuditLevel.HARD_FAIL, "结构失效后禁止扩大风险动作")
    return _finding("structure_invalidation", AuditLevel.PASS, "结构失效约束未被违反")


def audit_execution_price(
    *,
    side: OrderSide,
    execution_price: Decimal,
    allowed_low: Decimal,
    allowed_high: Decimal,
    reference_price: Decimal,
) -> AuditFinding:
    if allowed_low <= execution_price <= allowed_high:
        adverse = (
            (execution_price - reference_price) / reference_price
            if side is OrderSide.BUY
            else (reference_price - execution_price) / reference_price
        )
        level = AuditLevel.WARNING if adverse > Decimal("0.005") else AuditLevel.PASS
        return _finding("execution_price", level, "成交仍在计划边界内，按不利成交偏差分级")

    boundary = allowed_high if execution_price > allowed_high else allowed_low
    deviation = abs(execution_price - boundary) / boundary
    if deviation <= Decimal("0.005"):
        level = AuditLevel.WARNING
    elif deviation <= Decimal("0.01"):
        level = AuditLevel.OVERRIDABLE_FAIL
    else:
        level = AuditLevel.HARD_FAIL
    return _finding("execution_price", level, "真实成交越过计划价格边界")


def estimated_price_with_slippage(
    *, side: OrderSide, planned_price: Decimal, actual_price: Decimal | None = None
) -> Decimal:
    if actual_price is not None:
        return actual_price
    multiplier = Decimal("1") + DEFAULT_ONE_WAY_SLIPPAGE
    if side is OrderSide.SELL:
        multiplier = Decimal("1") - DEFAULT_ONE_WAY_SLIPPAGE
    return planned_price * multiplier


def apply_override(level: AuditLevel, *, user_confirmed: bool, reason: str | None) -> OverrideDecision:
    if level is AuditLevel.HARD_FAIL:
        return OverrideDecision(False, AuditLevel.HARD_FAIL, None)
    if level is not AuditLevel.OVERRIDABLE_FAIL:
        return OverrideDecision(True, level, None)
    clean_reason = reason.strip() if reason else ""
    if not user_confirmed or not clean_reason:
        return OverrideDecision(False, AuditLevel.OVERRIDABLE_FAIL, None)
    return OverrideDecision(True, AuditLevel.OVERRIDABLE_FAIL, clean_reason)
