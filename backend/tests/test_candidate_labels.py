"""Chinese presentation labels must cover every canonical M7 fact and state."""

from app.candidate.facts import HARD_RISKS, SOFT_RISKS
from app.candidate.labels import (
    PROFILE_LABELS,
    REVIEW_LANE_LABELS,
    RISK_LABELS,
    RISK_STATE_LABELS,
    STATUS_LABELS,
)


def test_all_known_risk_codes_have_chinese_names() -> None:
    assert set(RISK_LABELS) == HARD_RISKS | SOFT_RISKS
    assert all(any("\u4e00" <= char <= "\u9fff" for char in label) for label in RISK_LABELS.values())


def test_all_screening_states_and_profile_values_are_labeled() -> None:
    assert set(STATUS_LABELS) == {"CANDIDATE", "REVIEW", "EXCLUDED"}
    assert set(RISK_STATE_LABELS) == {"PRESENT", "ABSENT", "UNKNOWN"}
    assert set(REVIEW_LANE_LABELS) == {"C", "A", "B", None}
    assert set(PROFILE_LABELS) == {"board", "liquidity", "size", "listing_age"}
    assert set(PROFILE_LABELS["board"]) == {"MAIN", "OTHER", "UNKNOWN"}
    assert set(PROFILE_LABELS["liquidity"]) == {"GOOD", "LOW", "UNKNOWN"}
    assert set(PROFILE_LABELS["size"]) == {"MID_LARGE", "SMALL", "UNKNOWN"}
    assert set(PROFILE_LABELS["listing_age"]) == {"ESTABLISHED", "NEW", "UNKNOWN"}


def test_public_status_label() -> None:
    from app.candidate import status_label

    assert status_label("CANDIDATE") == "候选待人工判断"
    assert status_label("REVIEW") == "资料待核实"
    assert status_label("EXCLUDED") == "风险排除"


def test_chinese_projection_keeps_original_codes() -> None:
    from app.candidate import present_screening_result
    from app.candidate.engine import ScreeningResult
    from app.candidate.facts import Evidence, ObservedFact, RiskFact

    evidence = Evidence("fixture", "fixture://labels", "2026-10-16T04:00:00+08:00")
    result = ScreeningResult(
        symbol="TEST.SH", name="测试", status="EXCLUDED",
        review_lane=None, review_lane_evidence=None,
        profile_facts=tuple(ObservedFact(value, evidence) for value in (
            "MAIN", "GOOD", "MID_LARGE", "ESTABLISHED"
        )),
        reasons=(), risk_facts=(RiskFact("FINANCIAL_FRAUD", "PRESENT", evidence),),
        missing_risk_checks=("GOING_CONCERN",),
        messages=("排除：已确认重大风险 FINANCIAL_FRAUD",),
    )
    view = present_screening_result(result)
    assert view["status_label"] == "风险排除"
    assert view["risk_labels"] == ["财务造假"]
    assert view["risk_state_labels"] == ["已确认存在"]
    assert view["missing_risk_labels"] == ["持续经营风险"]
    assert view["profile_labels"] == ["主板", "流动性良好", "大中盘", "非次新"]
    assert "财务造假" in view["display_messages"][0]
    assert view["risk_facts"][0]["code"] == "FINANCIAL_FRAUD"
    assert view["risk_facts"][0]["evidence"]["reference"] == evidence.reference
