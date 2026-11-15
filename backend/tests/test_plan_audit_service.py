"""Pure tests for the plan-version audit rule composition."""

from __future__ import annotations

from decimal import Decimal

from app.domain.enums import AuditLevel
from app.services.plan_audit import PlanVersionFacts, audit_plan_version


def _facts(**overrides: object) -> PlanVersionFacts:
    base: dict[str, object] = {
        "entry_price_low": Decimal(10),
        "entry_price_high": Decimal("10.5"),
        "invalidation_price": Decimal("9.6"),
        "invalidation_condition": "收盘跌破9.60",
        "initial_entry_pct": Decimal(40),
        "confirmation_add_pct": Decimal(30),
        "t_reserve_pct": Decimal(30),
        "first_target_reduce_pct": Decimal(50),
        "planned_total_position_amount": None,
        "planned_total_position_pct": Decimal(30),
    }
    base.update(overrides)
    return PlanVersionFacts(**base)  # type: ignore[arg-type]


def test_full_inputs_pass_with_1_2_percent_risk() -> None:
    outcome = audit_plan_version(_facts(), Decimal(1000000))
    assert outcome.report.level is AuditLevel.PASS
    assert outcome.skipped == ()
    risk = next(item for item in outcome.report.findings if item.rule == "single_trade_risk")
    assert risk.level is AuditLevel.PASS
    completeness = [item for item in outcome.report.findings if item.rule == "plan_completeness"]
    assert completeness == []


def test_amount_is_derived_from_equity_and_total_pct() -> None:
    # 30% 总仓位 × 4% 亏损幅度 = 1.2% 单笔风险
    outcome = audit_plan_version(_facts(), Decimal(1000000))
    rules = {item.rule for item in outcome.report.findings}
    assert "single_trade_risk" in rules


def test_missing_equity_skips_risk_rule() -> None:
    outcome = audit_plan_version(_facts(), None)
    skipped = {item.rule for item in outcome.skipped}
    assert "single_trade_risk" in skipped
    assert "position_split" not in skipped


def test_missing_invalidation_fails_completeness() -> None:
    outcome = audit_plan_version(
        _facts(invalidation_price=None, invalidation_condition=None), Decimal(1000000)
    )
    completeness = next(
        item for item in outcome.report.findings if item.rule == "plan_completeness"
    )
    assert completeness.level is AuditLevel.OVERRIDABLE_FAIL
    assert outcome.report.level is AuditLevel.OVERRIDABLE_FAIL


def test_invalidation_at_or_above_entry_skips_risk() -> None:
    outcome = audit_plan_version(
        _facts(invalidation_price=Decimal("10.00")), Decimal(1000000)
    )
    assert "single_trade_risk" in {item.rule for item in outcome.skipped}


def test_warning_band_for_risk_between_2_and_3_percent() -> None:
    # 30% 总仓位 × 7% 亏损幅度 = 2.1% 单笔风险
    outcome = audit_plan_version(_facts(invalidation_price=Decimal("9.30")), Decimal(1000000))
    risk = next(item for item in outcome.report.findings if item.rule == "single_trade_risk")
    assert risk.level is AuditLevel.WARNING


def test_hard_fail_above_3_percent_risk() -> None:
    # 30% 总仓位 × 11% 亏损幅度 = 3.3% 单笔风险
    outcome = audit_plan_version(_facts(invalidation_price=Decimal("8.90")), Decimal(1000000))
    assert outcome.report.level is AuditLevel.HARD_FAIL


def test_out_of_range_split_is_overridable_fail() -> None:
    outcome = audit_plan_version(_facts(initial_entry_pct=Decimal(50)), Decimal(1000000))
    split = [item for item in outcome.report.findings if item.rule == "initial_position"]
    assert split[0].level is AuditLevel.OVERRIDABLE_FAIL


def test_missing_split_inputs_skip_position_rules() -> None:
    outcome = audit_plan_version(_facts(confirmation_add_pct=None), Decimal(1000000))
    skipped = {item.rule for item in outcome.skipped}
    assert "position_split" in skipped


def test_empty_inputs_only_fail_completeness() -> None:
    outcome = audit_plan_version(
        PlanVersionFacts(
            entry_price_low=None,
            entry_price_high=None,
            invalidation_price=None,
            invalidation_condition=None,
            initial_entry_pct=None,
            confirmation_add_pct=None,
            t_reserve_pct=None,
            first_target_reduce_pct=None,
            planned_total_position_amount=None,
            planned_total_position_pct=None,
        ),
        None,
    )
    assert outcome.report.level is AuditLevel.OVERRIDABLE_FAIL
    skipped = {item.rule for item in outcome.skipped}
    assert {"position_split", "single_trade_risk", "target_one"} <= skipped
