"""Timezone objects without a UTC offset are not valid observation timestamps."""
from datetime import datetime, timedelta, tzinfo
from decimal import Decimal

import pytest

from app.market_data.contracts import (
    Bar, DataQuality, DataResult, Quote, quality_at,
)


class OffsetUnavailable(tzinfo):
    def utcoffset(self, dt):
        return None

    def dst(self, dt):
        return None


INVALID = datetime(2026, 10, 12, 9, 30, tzinfo=OffsetUnavailable())


def test_data_result_rejects_non_resolving_fetch_timezone():
    with pytest.raises(ValueError, match="timezone"):
        DataResult(
            value=Quote(symbol="600000"), source="fixture",
            fetched_at=INVALID, observed_at=None,
            quality=DataQuality.UNVERIFIED,
        )


def test_data_result_rejects_non_resolving_observation_timezone():
    with pytest.raises(ValueError, match="timezone"):
        DataResult(
            value=Quote(symbol="600000"), source="fixture",
            fetched_at=datetime.now().astimezone(),
            observed_at=INVALID, quality=DataQuality.FRESH,
        )


def test_quality_at_rejects_non_resolving_fetch_timezone():
    with pytest.raises(ValueError, match="freshness inputs"):
        quality_at(None, INVALID, timedelta(minutes=15))


def test_bar_rejects_non_resolving_timezone():
    with pytest.raises(ValueError, match="timezone"):
        Bar(INVALID, Decimal(10), Decimal(12), Decimal(9), Decimal(11))


def test_quality_at_rejects_non_resolving_observation_timezone():
    with pytest.raises(ValueError, match="timezone"):
        quality_at(INVALID, datetime.now().astimezone(), timedelta(minutes=15))
