"""Provider-neutral market data types for objective observations."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Generic, Protocol, TypeVar


class DataQuality(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    UNVERIFIED = "UNVERIFIED"
    MISSING = "MISSING"
    ERROR = "ERROR"


class Timeframe(str, Enum):
    DAY = "1d"
    MIN5 = "5m"
    MIN15 = "15m"


@dataclass(frozen=True)
class Quote:
    symbol: str
    name: str | None = None
    last: Decimal | None = None
    previous_close: Decimal | None = None


T = TypeVar("T")


@dataclass(frozen=True)
class DataResult(Generic[T]):
    value: T | None
    source: str
    fetched_at: datetime
    observed_at: datetime | None
    quality: DataQuality


class MarketDataProvider(Protocol):
    def get_quote(self, symbol: str) -> DataResult[Quote]: ...
