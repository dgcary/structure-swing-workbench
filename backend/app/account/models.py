"""Typed provenance and immutable execution facts for M5."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


class ImportConflictError(ValueError):
    """An incoming record conflicts with already accepted facts."""


class SourceKind(str, Enum):
    PLAN = "plan"
    MANUAL = "manual"
    SNAPSHOT = "snapshot"
    CONFIRMED_FILL = "confirmed_fill"

    @property
    def priority(self) -> int:
        return {
            SourceKind.PLAN: 0,
            SourceKind.MANUAL: 1,
            SourceKind.SNAPSHOT: 2,
            SourceKind.CONFIRMED_FILL: 3,
        }[self]


class FillSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True, slots=True)
class Fact:
    key: str
    value: Decimal
    source: SourceKind
    source_id: str
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class Fill:
    fill_id: str
    symbol: str
    side: FillSide
    quantity: Decimal
    price: Decimal
    executed_at: datetime
    source_id: str


@dataclass(frozen=True, slots=True)
class AuditEvent:
    action: str
    key: str
    source_id: str
    detail: str


@dataclass(frozen=True, slots=True)
class Conflict:
    key: str
    existing: str
    incoming: str
    reason: str


@dataclass(frozen=True, slots=True)
class ImportResult:
    imported: int
    duplicates: int
    conflicts: int
    batch_duplicate: bool = False


@dataclass(frozen=True, slots=True)
class PositionView:
    symbol: str
    quantity: Decimal | None
    unanchored_fill_delta: Decimal
    broker_display_cost: Decimal | None
    baseline_as_of: datetime | None
    applied_fill_ids: tuple[str, ...]
