"""Composition of M2 rule functions for execution actions and fills.

Pure module: it reads standardized action/version facts, calls the rule
functions in ``app.audit.engine``, and never touches the database. Missing
inputs never fail silently: skipped rules are reported with a Chinese reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.audit.engine import (
    AuditFinding,
    AuditReport,
    aggregate,
    audit_confirmation_add,
    audit_execution_price,
    audit_initial_entry,
    audit_structure_invalidation,
)
from app.domain.enums import ActionType, AuditLevel, EntryMode, OrderSide

RISK_INCREASING_ACTIONS = frozenset(
    {
        ActionType.INITIAL_ENTRY,
        ActionType.CONFIRMATION_ADD,
        ActionType.ORDINARY_ADD,
        ActionType.POSITIVE_T_BUYBACK,
        ActionType.REVERSE_T_BUY,
    }
)

T_CYCLE_ACTIONS = frozenset(
    {
        ActionType.POSITIVE_T_SELL,
        ActionType.POSITIVE_T_BUYBACK,
        ActionType.REVERSE_T_BUY,
        ActionType.REVERSE_T_SELL,
    }
)

_SIDE_FOR_ACTION: dict[ActionType, OrderSide] = {
    ActionType.INITIAL_ENTRY: OrderSide.BUY,
    ActionType.CONFIRMATION_ADD: OrderSide.BUY,
    ActionType.ORDINARY_ADD: OrderSide.BUY,
    ActionType.POSITIVE_T_BUYBACK: OrderSide.BUY,
    ActionType.REVERSE_T_BUY: OrderSide.BUY,
    ActionType.POSITIVE_T_SELL: OrderSide.SELL,
    ActionType.REVERSE_T_SELL: OrderSide.SELL,
    ActionType.TAKE_PROFIT: OrderSide.SELL,
    ActionType.REDUCE: OrderSide.SELL,
    ActionType.STOP_EXIT: OrderSide.SELL,
    ActionType.EXIT_OTHER: OrderSide.SELL,
}


def expected_side(action_type: ActionType) -> OrderSide:
    return _SIDE_FOR_ACTION[action_type]


@dataclass(frozen=True, slots=True)
class ActionFacts:
    action_type: ActionType
    side: OrderSide
    planned_price_low: Decimal | None
    planned_price_high: Decimal | None
    t_cycle_key: str | None


@dataclass(frozen=True, slots=True)
class VersionFacts:
    entry_mode: EntryMode | None
    version_entry_low: Decimal | None
    version_entry_high: Decimal | None
    reversal_confirmed: bool | None
    confirmation_trigger_price: Decimal | None
    structure_invalidated: bool | None


@dataclass(frozen=True, slots=True)
class SkippedRule:
    rule: str
    reason: str


@dataclass(frozen=True, slots=True)
class ActionAuditOutcome:
    report: AuditReport
    skipped: tuple[SkippedRule, ...]


def audit_planned_action(
    version: VersionFacts, action: ActionFacts
) -> ActionAuditOutcome:
    """Audit an execution action before any fill is recorded."""

    findings: list[AuditFinding] = []
    skipped: list[SkippedRule] = []

    starts_new_t_cycle = (
        action.t_cycle_key is not None and action.action_type in T_CYCLE_ACTIONS
    )
    findings.append(
        audit_structure_invalidation(
            invalidated=version.structure_invalidated is True,
            action_type=action.action_type,
            starts_new_t_cycle=starts_new_t_cycle,
        )
    )

    if action.action_type is ActionType.INITIAL_ENTRY:
        if (
            version.entry_mode is not None
            and version.version_entry_low is not None
            and action.planned_price_low is not None
        ):
            findings.append(
                audit_initial_entry(
                    mode=version.entry_mode,
                    action_price=action.planned_price_low,
                    planned_price_low=version.version_entry_low,
                    planned_price_high=version.version_entry_high,
                )
            )
        else:
            skipped.append(
                SkippedRule(
                    rule="initial_entry",
                    reason="缺少建仓方式、计划建仓价或动作计划价，未检查初始建仓价格边界",
                )
            )

    if action.action_type is ActionType.CONFIRMATION_ADD:
        if (
            version.reversal_confirmed is not None
            and version.confirmation_trigger_price is not None
            and action.planned_price_low is not None
        ):
            findings.append(
                audit_confirmation_add(
                    reversal_confirmed=version.reversal_confirmed is True,
                    action_price=action.planned_price_low,
                    trigger_price=version.confirmation_trigger_price,
                )
            )
        else:
            skipped.append(
                SkippedRule(
                    rule="confirmation_add",
                    reason="缺少反转确认、加仓触发价或动作计划价，未检查确认加仓规则",
                )
            )

    return ActionAuditOutcome(aggregate(findings), tuple(skipped))


def audit_recorded_fill(
    version: VersionFacts,
    action: ActionFacts,
    *,
    fill_price: Decimal,
    fill_quantity: Decimal,
) -> ActionAuditOutcome:
    """Audit a real fill: risk-increasing blocks after invalidation, then price bounds."""

    findings: list[AuditFinding] = []
    skipped: list[SkippedRule] = []

    starts_new_t_cycle = (
        action.t_cycle_key is not None and action.action_type in T_CYCLE_ACTIONS
    )
    findings.append(
        audit_structure_invalidation(
            invalidated=version.structure_invalidated is True,
            action_type=action.action_type,
            starts_new_t_cycle=starts_new_t_cycle,
        )
    )

    if (
        action.planned_price_low is not None
        and action.planned_price_high is not None
        and fill_price > 0
    ):
        reference = (action.planned_price_low + action.planned_price_high) / Decimal(2)
        findings.append(
            audit_execution_price(
                side=action.side,
                execution_price=fill_price,
                allowed_low=action.planned_price_low,
                allowed_high=action.planned_price_high,
                reference_price=reference,
            )
        )
    else:
        skipped.append(
            SkippedRule(
                rule="execution_price",
                reason="动作缺少计划价格边界，未检查成交价格越界",
            )
        )

    return ActionAuditOutcome(aggregate(findings), tuple(skipped))


def blocked_by_hard_fail(outcome: ActionAuditOutcome) -> bool:
    return outcome.report.level is AuditLevel.HARD_FAIL
