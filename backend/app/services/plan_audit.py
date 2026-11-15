"""Composition of M2 rule functions for a plan-version audit subject.

This module stays pure: it reads standardized plan-version facts, calls the
rule functions in ``app.audit.engine``, and never touches the database, market
data or the LLM. Missing inputs never fail silently: each skipped rule is
reported with a Chinese reason so the user can see what was not checked.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.audit.engine import (
    AuditFinding,
    AuditReport,
    aggregate,
    audit_position_split,
    audit_single_trade_risk,
    audit_target_one,
)
from app.domain.enums import AuditLevel


@dataclass(frozen=True, slots=True)
class PlanVersionFacts:
    """Standardized plan-version inputs for the rule composition."""

    entry_price_low: Decimal | None
    entry_price_high: Decimal | None
    invalidation_price: Decimal | None
    invalidation_condition: str | None
    initial_entry_pct: Decimal | None
    confirmation_add_pct: Decimal | None
    t_reserve_pct: Decimal | None
    first_target_reduce_pct: Decimal | None
    planned_total_position_amount: Decimal | None
    planned_total_position_pct: Decimal | None


@dataclass(frozen=True, slots=True)
class SkippedRule:
    rule: str
    reason: str


@dataclass(frozen=True, slots=True)
class PlanVersionAuditOutcome:
    report: AuditReport
    skipped: tuple[SkippedRule, ...]


_COMPLETENESS_RULE = "plan_completeness"
_POSITION_SPLIT_RULE = "position_split"
_RISK_RULE = "single_trade_risk"
_TARGET_RULE = "target_one"


def audit_plan_version(
    facts: PlanVersionFacts, account_equity: Decimal | None
) -> PlanVersionAuditOutcome:
    """Run every rule whose inputs exist; report the rest as skipped.

    结构失效价与条件是正式计划的必备字段（trading-rules.md §7），缺失记为可覆盖失败，
    由用户通过覆盖流程决定是否继续。
    """

    findings: list[AuditFinding] = []
    skipped: list[SkippedRule] = []

    if facts.invalidation_price is None or not (
        facts.invalidation_condition or ""
    ).strip():
        findings.append(
            AuditFinding(
                rule=_COMPLETENESS_RULE,
                level=AuditLevel.OVERRIDABLE_FAIL,
                message="正式计划缺少结构失效价或结构失效条件",
            )
        )

    split_inputs = (
        facts.initial_entry_pct,
        facts.confirmation_add_pct,
        facts.t_reserve_pct,
    )
    if all(value is not None for value in split_inputs):
        findings.extend(
            audit_position_split(
                initial_pct=facts.initial_entry_pct,  # type: ignore[arg-type]
                confirmation_pct=facts.confirmation_add_pct,  # type: ignore[arg-type]
                t_reserve_pct=facts.t_reserve_pct,  # type: ignore[arg-type]
            )
        )
    else:
        skipped.append(
            SkippedRule(
                rule=_POSITION_SPLIT_RULE,
                reason="缺少初始建仓/确认加仓/T仓比例，未检查 40/30/30 仓位规则",
            )
        )

    risk_pct = _planned_risk_pct(facts, account_equity)
    if risk_pct is None:
        skipped.append(
            SkippedRule(
                rule=_RISK_RULE,
                reason="缺少建仓价、结构失效价、计划仓位或账户权益，未检查单笔账户风险",
            )
        )
    else:
        findings.append(audit_single_trade_risk(risk_pct))

    if facts.first_target_reduce_pct is not None:
        findings.extend(
            audit_target_one(
                reduce_pct=facts.first_target_reduce_pct, reached=False, completed=False
            )
        )
    else:
        skipped.append(
            SkippedRule(rule=_TARGET_RULE, reason="未设置第一目标减仓比例，未检查减仓比例范围")
        )

    return PlanVersionAuditOutcome(aggregate(findings), tuple(skipped))


def _planned_risk_pct(
    facts: PlanVersionFacts, account_equity: Decimal | None
) -> Decimal | None:
    """计划最大亏损 / 账户有效权益（trading-rules.md §4）。

    最大亏损按“买入参考价跌到结构失效价”计算；买入参考价取区间下沿（更保守）。
    """

    if (
        facts.entry_price_low is None
        or facts.invalidation_price is None
        or account_equity is None
        or account_equity <= 0
    ):
        return None
    if facts.entry_price_low <= 0 or facts.invalidation_price <= 0:
        return None
    if facts.invalidation_price >= facts.entry_price_low:
        return None

    position_amount = facts.planned_total_position_amount
    if position_amount is None and facts.planned_total_position_pct is not None:
        position_amount = account_equity * facts.planned_total_position_pct / Decimal(100)
    if position_amount is None or position_amount <= 0:
        return None

    loss_ratio = (facts.entry_price_low - facts.invalidation_price) / facts.entry_price_low
    max_loss = position_amount * loss_ratio
    return max_loss / account_equity * Decimal(100)
