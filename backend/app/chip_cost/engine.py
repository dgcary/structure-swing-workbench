"""Explainable, probabilistic A-share chip-cost estimates; never actual holdings.

All quantities are shares, turnover_rate is a fraction (0..1), and prices
must be unadjusted (raw). The model is deliberately not a trading signal.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_FLOOR, Decimal
from itertools import pairwise
from zoneinfo import ZoneInfo

from app.market_data.contracts import Bar, DataQuality

MODEL_VERSION = "turnover-decay-price-bins-v1"
ZERO = Decimal(0)
ONE = Decimal(1)
A_SHARE_TIMEZONE = ZoneInfo("Asia/Shanghai")


def _trading_date(timestamp: datetime):
    """Normalize provider timestamps to the A-share exchange calendar date."""
    return timestamp.astimezone(A_SHARE_TIMEZONE).date()


@dataclass(frozen=True, slots=True)
class DayObservation:
    bar: Bar
    turnover_rate: Decimal | None
    floating_shares: Decimal | None
    source: str
    quality: DataQuality
    minute_bars: tuple[Bar, ...] = ()
    split_factor: Decimal | None = None
    corporate_action_checked: bool = False
    price_basis: str = "raw"

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("source must not be empty")
        if self.price_basis != "raw":
            raise ValueError("adjusted prices cannot be mixed into raw-cost model")
        if self.turnover_rate is not None and (
            not self.turnover_rate.is_finite()
            or not ZERO <= self.turnover_rate <= ONE
        ):
            raise ValueError("turnover_rate must be between 0 and 1")
        if self.floating_shares is not None and (
            not self.floating_shares.is_finite() or self.floating_shares <= ZERO
        ):
            raise ValueError("floating_shares must be positive")
        if self.split_factor is not None and (
            not self.split_factor.is_finite() or self.split_factor <= ZERO
        ):
            raise ValueError("split_factor must be positive")
        if not isinstance(self.quality, DataQuality):
            raise TypeError("quality must be DataQuality")


@dataclass(frozen=True, slots=True)
class PriceBin:
    price: Decimal
    estimated_shares: Decimal
    fraction: Decimal


@dataclass(frozen=True, slots=True)
class CostMetrics:
    estimated_mean_cost: Decimal
    profitable_fraction: Decimal
    underwater_fraction: Decimal
    breakeven_fraction: Decimal
    interval_70: tuple[Decimal, Decimal]
    interval_90: tuple[Decimal, Decimal]
    concentration_10pct: Decimal


@dataclass(frozen=True, slots=True)
class DistributionResult:
    bins: tuple[PriceBin, ...]
    metrics: CostMetrics | None
    floating_shares: Decimal | None
    estimated_total: Decimal
    share_gap: Decimal | None
    source_quality: DataQuality
    warnings: tuple[str, ...]
    sources: tuple[str, ...]
    observed_at: datetime | None
    computed_at: datetime
    model_version: str = MODEL_VERSION


def _bucket(price: Decimal, width: Decimal) -> Decimal:
    return (price / width).to_integral_value(rounding=ROUND_FLOOR) * width


def _spread(
    output: dict[Decimal, Decimal],
    low: Decimal,
    high: Decimal,
    quantity: Decimal,
    width: Decimal,
) -> None:
    first = _bucket(low, width)
    last = _bucket(high, width)
    count = int((last - first) / width) + 1
    if count > 20000:
        raise ValueError("price range exceeds 20000 bins; choose a wider bin")
    each = quantity / Decimal(count)
    allocated = ZERO
    for index in range(count):
        # Assign the rounding remainder to the last bucket: no phantom share gap.
        portion = quantity - allocated if index == count - 1 else each
        output[first + width * index] += portion
        allocated += portion


def _new_shares(
    observation: DayObservation,
    traded_shares: Decimal,
    width: Decimal,
    warnings: list[str],
) -> dict[Decimal, Decimal]:
    result: dict[Decimal, Decimal] = defaultdict(Decimal)
    if traded_shares == ZERO:
        return result
    bars = observation.minute_bars
    if bars:
        same_day = all(
            _trading_date(bar.observed_at) == _trading_date(observation.bar.observed_at)
            for bar in bars
        )
        chronological = all(
            left.observed_at < right.observed_at for left, right in pairwise(bars)
        )
        valid_volumes = all(bar.volume is not None for bar in bars)
        within_daily_range = all(
            observation.bar.low <= bar.low <= bar.high <= observation.bar.high
            for bar in bars
        )
        minute_volume = sum((bar.volume or ZERO for bar in bars), ZERO)
        day_volume = observation.bar.volume
        # Volume units are source-specific; reject incompatible minute/day scales.
        consistent = (
            day_volume is not None
            and day_volume > ZERO
            and abs(minute_volume - day_volume) <= day_volume * Decimal("0.01")
        )
        if (
            same_day and chronological and valid_volumes and within_daily_range
            and minute_volume > ZERO and consistent
        ):
            allocated = ZERO
            for index, bar in enumerate(bars):
                # Give the last minute the remainder to avoid Decimal division drift.
                quantity = (
                    traded_shares - allocated
                    if index == len(bars) - 1
                    else traded_shares * bar.volume / minute_volume
                )
                _spread(result, bar.low, bar.high, quantity, width)
                allocated += quantity
            return result
        warnings.append("MINUTE_DATA_REJECTED_DAILY_FALLBACK")
    warnings.append("DAILY_UNIFORM_PRICE_APPROXIMATION")
    _spread(result, observation.bar.low, observation.bar.high, traded_shares, width)
    return result


def _percentile(ordered: list[tuple[Decimal, Decimal]], target: Decimal) -> Decimal:
    cumulative = ZERO
    total = sum((quantity for _, quantity in ordered), ZERO)
    for price, quantity in ordered:
        cumulative += quantity
        if cumulative >= total * target:
            return price
    return ordered[-1][0]


def _metrics(
    ordered: list[tuple[Decimal, Decimal]], reference_price: Decimal, total: Decimal,
) -> CostMetrics:
    profitable = sum((q for p, q in ordered if p < reference_price), ZERO)
    underwater = sum((q for p, q in ordered if p > reference_price), ZERO)
    breakeven = total - profitable - underwater
    lower = reference_price * Decimal("0.95")
    upper = reference_price * Decimal("1.05")
    concentrated = sum((q for p, q in ordered if lower <= p <= upper), ZERO)
    return CostMetrics(
        estimated_mean_cost=sum((p * q for p, q in ordered), ZERO) / total,
        profitable_fraction=profitable / total,
        underwater_fraction=underwater / total,
        breakeven_fraction=breakeven / total,
        interval_70=(
            _percentile(ordered, Decimal("0.15")),
            _percentile(ordered, Decimal("0.85")),
        ),
        interval_90=(
            _percentile(ordered, Decimal("0.05")),
            _percentile(ordered, Decimal("0.95")),
        ),
        concentration_10pct=concentrated / total,
    )


def estimate_distribution(
    observations: tuple[DayObservation, ...],
    *,
    bin_width: Decimal = Decimal("0.10"),
    computed_at: datetime | None = None,
) -> DistributionResult:
    """Replay observations oldest-first with probabilistic turnover decay.

    First day's untraded float is bootstrapped at its close; this is an
    explicit estimation assumption, not a reconstruction of prior holdings.
    """
    if not bin_width.is_finite() or bin_width <= ZERO:
        raise ValueError("bin_width must be positive and finite")
    now = computed_at or datetime.now(UTC)
    if now.utcoffset() is None:
        raise ValueError("computed_at must include timezone")
    if any(
        _trading_date(left.bar.observed_at) >= _trading_date(right.bar.observed_at)
        for left, right in pairwise(observations)
    ):
        raise ValueError("daily observations must be strictly chronological by trading date")
    warnings: list[str] = []
    sources = tuple(dict.fromkeys(item.source for item in observations))
    if not observations:
        return DistributionResult(
            (), None, None, ZERO, None, DataQuality.MISSING,
            ("EMPTY_HISTORY",), (), None, now,
        )

    quality_order = {
        DataQuality.FRESH: 0,
        DataQuality.STALE: 1,
        DataQuality.UNVERIFIED: 2,
        DataQuality.MISSING: 3,
        DataQuality.ERROR: 4,
    }
    quality = max((item.quality for item in observations), key=quality_order.__getitem__)
    # A positive turnover cannot be inferred from a reported zero-volume day.
    # Fail closed rather than creating fictional traded cost buckets.
    volume_conflict = any(
        item.bar.volume == ZERO
        and item.turnover_rate is not None
        and item.turnover_rate > ZERO
        for item in observations
    )
    if any(
        item.turnover_rate is None or item.floating_shares is None
        or item.bar.volume is None
        for item in observations
    ) or quality in (DataQuality.MISSING, DataQuality.ERROR) or volume_conflict:
        warnings.append("INCOMPLETE_OR_UNTRUSTED_HISTORY")
        if volume_conflict:
            warnings.append("TURNOVER_VOLUME_CONFLICT")
        return DistributionResult(
            (), None, observations[-1].floating_shares, ZERO, None,
            DataQuality.ERROR if quality is DataQuality.ERROR or volume_conflict
            else DataQuality.MISSING,
            tuple(warnings), sources, observations[-1].bar.observed_at, now,
        )

    # A zero turnover rate alongside nonzero volume can be caused by
    # provider rounding or incompatible units. Keep the estimate but expose
    # uncertainty instead of silently treating it as verified input.
    if any(
        day.turnover_rate == ZERO and day.bar.volume > ZERO
        for day in observations
    ):
        warnings.append("ZERO_TURNOVER_WITH_POSITIVE_VOLUME")
        if quality_order[quality] < quality_order[DataQuality.UNVERIFIED]:
            quality = DataQuality.UNVERIFIED

    shares: dict[Decimal, Decimal] = defaultdict(Decimal)
    previous_float: Decimal | None = None
    for day in observations:
        current_float = day.floating_shares
        if not day.corporate_action_checked:
            warnings.append("CORPORATE_ACTION_UNVERIFIED")
        if previous_float is None:
            warnings.append("INITIAL_COST_BOOTSTRAP")
            untraded = current_float * (ONE - day.turnover_rate)
            shares[_bucket(day.bar.close, bin_width)] += untraded
        else:
            factor = day.split_factor or ONE
            if factor != ONE:
                transformed: dict[Decimal, Decimal] = defaultdict(Decimal)
                for price, quantity in shares.items():
                    transformed[_bucket(price / factor, bin_width)] += quantity * factor
                shares = transformed
                warnings.append("SPLIT_REBASED")
            existing = sum(shares.values(), ZERO)
            delta = current_float - existing
            if delta > ZERO:
                shares[_bucket(day.bar.close, bin_width)] += delta
                warnings.append("FLOAT_INCREASE_ESTIMATED_AT_CLOSE")
            elif delta < ZERO:
                multiplier = current_float / existing
                shares = defaultdict(
                    Decimal, {price: qty * multiplier for price, qty in shares.items()}
                )
                warnings.append("FLOAT_DECREASE_PROPORTIONAL_ESTIMATE")
            for price in tuple(shares):
                shares[price] *= ONE - day.turnover_rate
        additions = _new_shares(
            day, current_float * day.turnover_rate, bin_width, warnings,
        )
        for price, quantity in additions.items():
            shares[price] += quantity
        previous_float = current_float

    total = sum(shares.values(), ZERO)
    ordered = sorted((price, quantity) for price, quantity in shares.items() if quantity > ZERO)
    bins = tuple(PriceBin(price, qty, qty / total) for price, qty in ordered)
    metrics = _metrics(ordered, observations[-1].bar.close, total)
    return DistributionResult(
        bins=bins, metrics=metrics, floating_shares=previous_float,
        estimated_total=total, share_gap=total - previous_float,
        source_quality=quality, warnings=tuple(dict.fromkeys(warnings)),
        sources=sources, observed_at=observations[-1].bar.observed_at,
        computed_at=now,
    )
