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
    "screen_candidate",
    "screen_candidates",
    "status_label",
]
