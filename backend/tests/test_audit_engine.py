from decimal import Decimal

import pytest

from app.audit.engine import (
    DEFAULT_ONE_WAY_SLIPPAGE,
    AuditFinding,
    aggregate,
    apply_override,
    audit_confirmation_add,
    audit_execution_price,
    audit_initial_entry,
    audit_position_split,
    audit_single_trade_risk,
    audit_structure_invalidation,
    audit_target_one,
    estimated_price_with_slippage,
)
from app.domain.enums import ActionType, AuditLevel, EntryMode, OrderSide


@pytest.mark.parametrize(
    ("risk", "expected"),
    [
        ("1.9999", AuditLevel.PASS),
        ("2", AuditLevel.PASS),
        ("2.0001", AuditLevel.WARNING),
        ("2.9999", AuditLevel.WARNING),
        ("3", AuditLevel.WARNING),
        ("3.0001", AuditLevel.HARD_FAIL),
    ],
)
def test_single_trade_risk_boundaries(risk: str, expected: AuditLevel) -> None:
    assert audit_single_trade_risk(Decimal(risk)).level is expected


@pytest.mark.parametrize(
    ("initial", "confirmation", "reserve", "expected"),
    [
        ("35", "25", "25", [AuditLevel.PASS] * 3),
        ("45", "35", "35", [AuditLevel.PASS] * 3),
        ("34.9999", "24.9999", "24.9999", [AuditLevel.WARNING] * 3),
        ("45.0001", "35.0001", "35.0001", [AuditLevel.WARNING] * 3),
    ],
)
def test_position_split_boundaries(initial, confirmation, reserve, expected) -> None:
    findings = audit_position_split(
        initial_pct=Decimal(initial),
        confirmation_pct=Decimal(confirmation),
        t_reserve_pct=Decimal(reserve),
    )
    assert [item.level for item in findings] == expected


def test_single_price_entry_cannot_chase_up() -> None:
    assert audit_initial_entry(
        mode=EntryMode.SINGLE_PRICE,
        execution_price=Decimal(10),
        planned_price_low=Decimal(10),
    ).level is AuditLevel.PASS
    assert audit_initial_entry(
        mode=EntryMode.SINGLE_PRICE,
        execution_price=Decimal("10.0001"),
        planned_price_low=Decimal(10),
    ).level is AuditLevel.HARD_FAIL


def test_range_entry_lower_two_percent_boundary() -> None:
    common = {"mode": EntryMode.PRICE_RANGE, "planned_price_low": Decimal(10), "planned_price_high": Decimal(11)}
    assert audit_initial_entry(execution_price=Decimal("9.8"), **common).level is AuditLevel.PASS
    assert audit_initial_entry(execution_price=Decimal("9.7999"), **common).level is AuditLevel.HARD_FAIL
    assert audit_initial_entry(execution_price=Decimal(11), **common).level is AuditLevel.PASS
    assert audit_initial_entry(execution_price=Decimal("11.0001"), **common).level is AuditLevel.HARD_FAIL


def test_confirmation_add_requires_confirmation_trigger_and_three_percent_cap() -> None:
    trigger = Decimal(10)
    assert audit_confirmation_add(
        reversal_confirmed=False, execution_price=trigger, trigger_price=trigger
    ).level is AuditLevel.HARD_FAIL
    assert audit_confirmation_add(
        reversal_confirmed=True, execution_price=Decimal("9.9999"), trigger_price=trigger
    ).level is AuditLevel.HARD_FAIL
    assert audit_confirmation_add(
        reversal_confirmed=True, execution_price=Decimal("10.3"), trigger_price=trigger
    ).level is AuditLevel.PASS
    assert audit_confirmation_add(
        reversal_confirmed=True, execution_price=Decimal("10.3001"), trigger_price=trigger
    ).level is AuditLevel.HARD_FAIL


@pytest.mark.parametrize(
    ("pct", "level"),
    [("39.9999", AuditLevel.WARNING), ("40", AuditLevel.PASS), ("60", AuditLevel.PASS), ("60.0001", AuditLevel.WARNING)],
)
def test_target_one_reduce_pct_boundaries(pct: str, level: AuditLevel) -> None:
    assert audit_target_one(reduce_pct=Decimal(pct), reached=False, completed=False)[0].level is level


def test_target_one_reached_but_not_completed_warns() -> None:
    findings = audit_target_one(reduce_pct=Decimal(50), reached=True, completed=False)
    assert findings[1].level is AuditLevel.WARNING


def test_structure_invalidation_blocks_risk_increasing_action() -> None:
    assert audit_structure_invalidation(
        invalidated=True, action_type=ActionType.CONFIRMATION_ADD
    ).level is AuditLevel.HARD_FAIL
    assert audit_structure_invalidation(
        invalidated=True, action_type=ActionType.STOP_EXIT
    ).level is AuditLevel.PASS


@pytest.mark.parametrize(
    ("price", "level"),
    [
        ("11.055", AuditLevel.WARNING),
        ("11.05501", AuditLevel.OVERRIDABLE_FAIL),
        ("11.11", AuditLevel.OVERRIDABLE_FAIL),
        ("11.1101", AuditLevel.HARD_FAIL),
    ],
)
def test_execution_price_outside_boundary_grades(price: str, level: AuditLevel) -> None:
    finding = audit_execution_price(
        side=OrderSide.BUY,
        execution_price=Decimal(price),
        allowed_low=Decimal(10),
        allowed_high=Decimal(11),
        reference_price=Decimal("10.5"),
    )
    assert finding.level is level


def test_execution_inside_boundary_uses_adverse_deviation() -> None:
    assert audit_execution_price(
        side=OrderSide.BUY,
        execution_price=Decimal("10.5525"),
        allowed_low=Decimal(10),
        allowed_high=Decimal(11),
        reference_price=Decimal("10.5"),
    ).level is AuditLevel.PASS
    assert audit_execution_price(
        side=OrderSide.BUY,
        execution_price=Decimal("10.5526"),
        allowed_low=Decimal(10),
        allowed_high=Decimal(11),
        reference_price=Decimal("10.5"),
    ).level is AuditLevel.WARNING


def test_aggregate_uses_highest_severity_without_warning_escalation() -> None:
    warnings = [AuditFinding(str(i), AuditLevel.WARNING, "警告") for i in range(10)]
    assert aggregate(warnings).level is AuditLevel.WARNING
    mixed = warnings + [AuditFinding("x", AuditLevel.OVERRIDABLE_FAIL, "可覆盖失败")]
    assert aggregate(mixed).level is AuditLevel.OVERRIDABLE_FAIL


def test_default_slippage_and_real_fill_precedence() -> None:
    assert DEFAULT_ONE_WAY_SLIPPAGE == Decimal("0.002")
    assert estimated_price_with_slippage(
        side=OrderSide.BUY, planned_price=Decimal(10)
    ) == Decimal("10.020")
    assert estimated_price_with_slippage(
        side=OrderSide.SELL, planned_price=Decimal(10)
    ) == Decimal("9.980")
    assert estimated_price_with_slippage(
        side=OrderSide.BUY, planned_price=Decimal(10), actual_price=Decimal("10.01")
    ) == Decimal("10.01")


def test_override_requires_confirmation_and_reason_and_never_overrides_hard_fail() -> None:
    assert not apply_override(
        AuditLevel.OVERRIDABLE_FAIL, user_confirmed=False, reason="接受偏差"
    ).allowed
    assert not apply_override(
        AuditLevel.OVERRIDABLE_FAIL, user_confirmed=True, reason="   "
    ).allowed
    allowed = apply_override(
        AuditLevel.OVERRIDABLE_FAIL, user_confirmed=True, reason="接受本次成交偏差"
    )
    assert allowed.allowed
    assert allowed.reason == "接受本次成交偏差"
    assert not apply_override(
        AuditLevel.HARD_FAIL, user_confirmed=True, reason="仍要继续"
    ).allowed


def test_structure_invalidation_new_cycle_flag() -> None:
    result = audit_structure_invalidation(
        invalidated=True,
        action_type=ActionType.POSITIVE_T_SELL,
        starts_new_t_cycle=True,
    )
    assert result.level is AuditLevel.HARD_FAIL
