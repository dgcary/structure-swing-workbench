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
