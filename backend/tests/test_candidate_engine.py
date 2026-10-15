"""Deterministic M7 fixtures: only supplied facts, no automatic trade decisions."""

from dataclasses import replace

import pytest

from app.candidate.engine import CandidateInput, screen_candidate, screen_candidates
from app.candidate.facts import HARD_RISKS, Evidence, ObservedFact, RiskFact

E = Evidence("synthetic-fixture", "fixture://m7/2026-10-15", "2026-10-15T08:00:00+08:00")


def sample(symbol: str = "DEMO001.SH", lane: str | None = "C") -> CandidateInput:
    return CandidateInput(
        symbol=symbol,
        name="合成证券",
        board=ObservedFact("MAIN", E),
        liquidity=ObservedFact("GOOD", E),
        size=ObservedFact("MID_LARGE", E),
        listing_age=ObservedFact("ESTABLISHED", E),
        risks=tuple(RiskFact(code, "ABSENT", E) for code in sorted(HARD_RISKS)),
        review_lane=lane,
        review_lane_evidence=E if lane else None,
    )


def test_evidence_and_priority_are_explicit_not_detected_setup() -> None:
    results = screen_candidates((
        sample("DEMO003.SH", "B"),
        sample("DEMO002.SH", "A"),
        sample("DEMO001.SH", "C"),
        sample("DEMO004.SH", None),
    ))
    assert [r.review_lane for r in results] == ["C", "A", "B", None]
    assert all(r.status == "CANDIDATE" for r in results)
    assert all(len(r.reasons) == 4 for r in results)
    assert results[0].reasons[0].evidence.reference == E.reference
    assert results[0].review_lane_evidence == E
    view = results[0].to_dict()
    assert "trade_action" not in view
    assert "buy_signal" not in view
    assert "setup_confirmed" not in view
    assert any("不代表 Setup 成立" in s for s in results[0].messages)


@pytest.mark.parametrize("code", sorted(HARD_RISKS))
def test_each_confirmed_red_line_is_excluded(code: str) -> None:
    item = sample()
    risks = tuple(
        replace(risk, state="PRESENT") if risk.code == code else risk
        for risk in item.risks
    )
    result = screen_candidate(replace(item, risks=risks))
    assert result.status == "EXCLUDED"
    assert any(code in message for message in result.messages)
    assert result.risk_facts[0].evidence.source == "synthetic-fixture"


def test_missing_and_unknown_red_line_are_not_silently_cleared() -> None:
    item = sample()
    missing = screen_candidate(replace(item, risks=item.risks[1:]))
    assert missing.status == "REVIEW"
    assert missing.missing_risk_checks
    unknown_risks = (replace(item.risks[0], state="UNKNOWN"),) + item.risks[1:]
    assert screen_candidate(replace(item, risks=unknown_risks)).status == "REVIEW"


def test_ordinary_earnings_decline_and_high_valuation_are_not_hard_exclusions() -> None:
    item = sample()
    soft = (
        RiskFact("EARNINGS_DECLINE", "PRESENT", E),
        RiskFact("VALUATION_HIGH", "PRESENT", E),
    )
    result = screen_candidate(replace(item, risks=item.risks + soft))
    assert result.status == "CANDIDATE"
    assert any("人工核查" in message for message in result.messages)


def test_low_liquidity_or_new_listing_excluded_without_inventing_setup() -> None:
    item = sample()
    assert screen_candidate(
        replace(item, liquidity=ObservedFact("LOW", E))
    ).status == "EXCLUDED"
    assert screen_candidate(
        replace(item, listing_age=ObservedFact("NEW", E))
    ).status == "EXCLUDED"
    assert screen_candidate(
        replace(item, size=ObservedFact("SMALL", E))
    ).status == "CANDIDATE"


def test_unknown_basic_facts_require_review() -> None:
    item = sample()
    result = screen_candidate(replace(item, board=ObservedFact("UNKNOWN", E)))
    assert result.status == "REVIEW"


def test_reject_unproven_review_lane_and_duplicate_risks() -> None:
    item = sample()
    with pytest.raises(ValueError, match="证据"):
        replace(item, review_lane_evidence=None)
    with pytest.raises(ValueError, match="重复"):
        replace(item, risks=item.risks + (item.risks[0],))
    with pytest.raises(ValueError, match="重复"):
        screen_candidates((item, item))


def test_reject_invalid_provenance_and_unrecognized_risk_state() -> None:
    with pytest.raises(ValueError, match="时区"):
        Evidence("fixture", "fixture://m7", "2026-10-15T08:00:00")
    with pytest.raises(ValueError, match="风险"):
        RiskFact("ST", "SUSPECTED", E)


def test_reject_missing_fact_provenance() -> None:
    with pytest.raises(TypeError, match="证据"):
        ObservedFact("GOOD", None)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="证据"):
        RiskFact("ST", "ABSENT", None)  # type: ignore[arg-type]
