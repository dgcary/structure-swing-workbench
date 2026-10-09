"""Provider-neutral, factual market-data contracts."""
from dataclasses import dataclass
from datetime import datetime, timedelta
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


@dataclass(frozen=True, slots=True)
class Quote:
    symbol: str
    name: str | None = None
    last: Decimal | None = None
    previous_close: Decimal | None = None
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    close: Decimal | None = None
    change_pct: Decimal | None = None
    limit_up: Decimal | None = None
    limit_down: Decimal | None = None
    volume: Decimal | None = None
    amount: Decimal | None = None
    turnover_pct: Decimal | None = None
    amplitude_pct: Decimal | None = None


@dataclass(frozen=True, slots=True)
class Bar:
    observed_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None = None
    amount: Decimal | None = None


@dataclass(frozen=True, slots=True)
class SecurityInfo:
    symbol: str
    name: str | None = None
    industry: str | None = None
    exchange: str | None = None
    suspended: bool | None = None
    is_st: bool | None = None
    delisting_risk: bool | None = None


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class DataResult(Generic[T]):
    value: T | None
    source: str
    fetched_at: datetime
    observed_at: datetime | None
    quality: DataQuality
    missing_fields: tuple[str, ...] = ()
    error: str | None = None

    def __post_init__(self) -> None:
        if self.fetched_at.tzinfo is None:
            raise ValueError("fetched_at must include a timezone")
        if self.observed_at is not None and self.observed_at.tzinfo is None:
            raise ValueError("observed_at must include a timezone")
        if self.value is None and self.quality in (
            DataQuality.FRESH, DataQuality.STALE, DataQuality.UNVERIFIED,
        ):
            raise ValueError("data without a value must be MISSING or ERROR")
        if self.value is not None and self.quality is DataQuality.MISSING:
            raise ValueError("MISSING cannot contain a data value")
        if self.quality in (DataQuality.FRESH, DataQuality.STALE) and self.observed_at is None:
            raise ValueError("FRESH/STALE require a source observation timestamp")


def quality_at(
    observed_at: datetime | None, fetched_at: datetime, max_age: timedelta,
) -> DataQuality:
    """A fetch timestamp alone cannot establish observation freshness."""
    if fetched_at.tzinfo is None or max_age.total_seconds() < 0:
        raise ValueError("invalid freshness inputs")
    if observed_at is None:
        return DataQuality.UNVERIFIED
    if observed_at.tzinfo is None:
        raise ValueError("observed_at must include a timezone")
    age = fetched_at - observed_at
    if age < -timedelta(minutes=5):
        return DataQuality.ERROR
    return DataQuality.STALE if age > max_age else DataQuality.FRESH


class MarketDataProvider(Protocol):
    def get_quote(self, symbol: str) -> DataResult[Quote]: ...

    def get_bars(self, symbol: str, timeframe: Timeframe) -> DataResult[tuple[Bar, ...]]: ...

    def get_security(self, symbol: str) -> DataResult[SecurityInfo]: ...


def moving_average(bars: tuple[Bar, ...], window: int) -> Decimal | None:
    if window <= 0:
        raise ValueError("window must be positive")
    if len(bars) < window:
        return None
    return sum((bar.close for bar in bars[-window:]), Decimal(0)) / Decimal(window)


def period_extrema(bars: tuple[Bar, ...], window: int) -> tuple[Decimal, Decimal] | None:
    if window <= 0:
        raise ValueError("window must be positive")
    if len(bars) < window:
        return None
    recent = bars[-window:]
    return max(bar.high for bar in recent), min(bar.low for bar in recent)
