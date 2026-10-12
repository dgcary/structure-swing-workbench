"""M4 quality contracts must explain provider failures instead of silently failing."""
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.market_data.contracts import DataQuality, DataResult, Quote

NOW = datetime(2026, 10, 12, 6, 0, tzinfo=UTC)


@pytest.mark.parametrize("reason", [None, "", "  "])
def test_error_status_requires_a_meaningful_reason(reason):
    with pytest.raises(ValueError, match="non-empty error reason"):
        DataResult(
            value=None, source="fixture", fetched_at=NOW,
            observed_at=None, quality=DataQuality.ERROR, error=reason,
        )


def test_error_status_can_preserve_partial_facts_with_explicit_reason():
    result = DataResult(
        value=Quote(symbol="600000", last=Decimal("10.5")),
        source="fixture", fetched_at=NOW, observed_at=None,
        quality=DataQuality.ERROR, error="security metadata endpoint unavailable",
    )
    assert result.value.last == Decimal("10.5")
    assert result.error == "security metadata endpoint unavailable"
    assert result.quality is DataQuality.ERROR
