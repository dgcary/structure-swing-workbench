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
