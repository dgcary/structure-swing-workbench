"""Provider-neutral bars must reject impossible source facts before math is applied."""
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.market_data.contracts import Bar

NOW = datetime(2026, 10, 9, 14, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
BASE = {
    "observed_at": NOW,
    "open": Decimal(10),
    "high": Decimal(11),
    "low": Decimal(9),
    "close": Decimal("10.5"),
    "volume": Decimal(0),
    "amount": Decimal(0),
}


def test_valid_provider_neutral_bar_allows_zero_trading_volume():
    bar = Bar(**BASE)
    assert bar.volume == 0
    assert bar.close == Decimal("10.5")


@pytest.mark.parametrize("changes,message", [
    ({"observed_at": NOW.replace(tzinfo=None)}, "timezone"),
    ({"open": Decimal(0)}, "positive and finite"),
    ({"high": Decimal("NaN")}, "positive and finite"),
    ({"low": Decimal("Infinity")}, "positive and finite"),
    ({"high": Decimal(8)}, "inconsistent"),
    ({"close": Decimal(12)}, "inconsistent"),
    ({"volume": Decimal(-1)}, "nonnegative and finite"),
    ({"amount": Decimal("NaN")}, "nonnegative and finite"),
])
def test_invalid_provider_neutral_bar_is_rejected(changes, message):
    with pytest.raises(ValueError, match=message):
        Bar(**{**BASE, **changes})
