"""M7 evidence-backed candidate review; never a trading signal."""

from app.candidate.engine import (
    CandidateInput,
    ScreeningResult,
    screen_candidate,
    screen_candidates,
)
from app.candidate.facts import Evidence, ObservedFact, RiskFact
from app.candidate.labels import PROFILE_LABELS, RISK_LABELS, RISK_STATE_LABELS, STATUS_LABELS

def status_label(status: str) -> str:
    """Chinese label for a canonical candidate status."""
    return STATUS_LABELS[status]


def present_screening_result(result: ScreeningResult) -> dict[str, object]:
    """Add Chinese labels without replacing the original codes and evidence."""
    payload = result.to_dict()
    payload["status_label"] = status_label(result.status)
    payload["risk_labels"] = [RISK_LABELS[risk.code] for risk in result.risk_facts]
    return payload


__all__ = [
    "PROFILE_LABELS",
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
