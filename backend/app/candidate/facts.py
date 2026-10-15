"""Provenance-linked candidate facts."""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Evidence:
    source: str
    reference: str
    observed_at: str


@dataclass(frozen=True, slots=True)
class ObservedFact:
    value: str
    evidence: Evidence


@dataclass(frozen=True, slots=True)
class RiskFact:
    code: str
    state: str
    evidence: Evidence

    def __post_init__(self) -> None:
        if self.state not in ("PRESENT", "ABSENT", "UNKNOWN"):
            raise ValueError("风险事实状态不合法")

HARD_RISKS = frozenset({
    "ST", "DELISTING", "REGULATORY_INVESTIGATION",
    "FINANCIAL_FRAUD", "QUALIFIED_AUDIT", "SEVERE_DEBT", "GOING_CONCERN",
})
