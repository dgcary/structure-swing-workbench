"""M7 evidence-backed candidate review; never a trading signal."""

from app.candidate.engine import (
    CandidateInput,
    ScreeningResult,
    screen_candidate,
    screen_candidates,
)
from app.candidate.facts import Evidence, ObservedFact, RiskFact
from app.candidate.labels import (
    PROFILE_LABELS,
    REVIEW_LANE_LABELS,
    RISK_LABELS,
    RISK_STATE_LABELS,
    STATUS_LABELS,
)

def status_label(status: str) -> str:
    """Chinese label for a canonical candidate status."""
    return STATUS_LABELS[status]


def present_screening_result(result: ScreeningResult) -> dict[str, object]:
    """Add Chinese labels without replacing the original codes and evidence."""
    payload = result.to_dict()
    payload["status_label"] = status_label(result.status)
    payload["review_lane_label"] = REVIEW_LANE_LABELS[result.review_lane]
    payload["profile_labels"] = [
        PROFILE_LABELS[field][fact.value]
        for field, fact in zip(
            ("board", "liquidity", "size", "listing_age"),
            result.profile_facts,
            strict=True,
        )
    ]
    payload["risk_labels"] = [RISK_LABELS[risk.code] for risk in result.risk_facts]
    payload["risk_state_labels"] = [
        RISK_STATE_LABELS[risk.state] for risk in result.risk_facts
    ]
    payload["missing_risk_labels"] = [
        RISK_LABELS[code] for code in result.missing_risk_checks
    ]
    display_messages = []
    for message in result.messages:
        for code in sorted(RISK_LABELS, key=len, reverse=True):
            message = message.replace(code, RISK_LABELS[code])
        display_messages.append(message)
    payload["display_messages"] = display_messages
    return payload


__all__ = [
    "PROFILE_LABELS",
    "REVIEW_LANE_LABELS",
    "RISK_LABELS",
    "RISK_STATE_LABELS",
    "STATUS_LABELS",
    "CandidateInput",
    "Evidence",
    "ObservedFact",
    "RiskFact",
    "ScreeningResult",
    "present_screening_result",
    "screen_candidate",
    "screen_candidates",
    "status_label",
]
