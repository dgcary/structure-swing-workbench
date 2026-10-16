"""M7 synthetic boundary fixtures for source-backed candidate screening."""

from dataclasses import replace

import pytest

from app.candidate.engine import CandidateInput
from app.candidate.facts import HARD_RISKS, Evidence, ObservedFact, RiskFact

EVIDENCE = Evidence("fixture", "fixture://m7/boundary", "2026-10-15T08:00:00+08:00")


def candidate() -> CandidateInput:
    return CandidateInput(
        symbol="TEST001.SH",
        name="合成证券",
        board=ObservedFact("MAIN", EVIDENCE),
        liquidity=ObservedFact("GOOD", EVIDENCE),
        size=ObservedFact("MID_LARGE", EVIDENCE),
        listing_age=ObservedFact("ESTABLISHED", EVIDENCE),
        risks=tuple(RiskFact(code, "ABSENT", EVIDENCE) for code in sorted(HARD_RISKS)),
        review_lane="C",
        review_lane_evidence=EVIDENCE,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("board", "INVALID"),
        ("liquidity", "HIGH"),
        ("size", "LARGE"),
        ("listing_age", "OLD"),
    ],
)
def test_reject_invalid_profile_categories(field: str, value: str) -> None:
    with pytest.raises(ValueError, match="分类值"):
        replace(candidate(), **{field: ObservedFact(value, EVIDENCE)})


@pytest.mark.parametrize("field", ["board", "liquidity", "size", "listing_age"])
def test_reject_profile_values_without_evidence(field: str) -> None:
    with pytest.raises(TypeError, match="ObservedFact"):
        replace(candidate(), **{field: "MAIN"})


def test_reject_unverifiable_review_lane() -> None:
    item = candidate()
    with pytest.raises(ValueError, match="复核通道"):
        replace(item, review_lane="D")
    with pytest.raises(ValueError, match="证据"):
        replace(item, review_lane=None)
    with pytest.raises(TypeError, match="Evidence"):
        replace(item, review_lane_evidence="unverified")


def test_reject_risk_records_without_source_links() -> None:
    item = candidate()
    with pytest.raises(TypeError, match="RiskFact"):
        replace(item, risks=list(item.risks))
    with pytest.raises(TypeError, match="RiskFact"):
        replace(item, risks=item.risks + ("ST",))
    with pytest.raises(ValueError, match="风险"):
        RiskFact("UNLISTED_RISK", "ABSENT", EVIDENCE)
