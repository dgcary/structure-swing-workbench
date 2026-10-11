"""Ensure every market-data result identifies its provider."""

from datetime import UTC, datetime

import pytest

from app.market_data.contracts import DataQuality, DataResult, Quote


def test_result_rejects_empty_provider_source():
    for source in ("", "   "):
        with pytest.raises(ValueError, match="source must identify"):
            DataResult(
                value=Quote(symbol="600000"), source=source,
                fetched_at=datetime(2026, 10, 11, tzinfo=UTC),
                observed_at=None, quality=DataQuality.UNVERIFIED,
            )
