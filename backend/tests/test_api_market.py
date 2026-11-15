"""Market-data API tests with an injected fake provider."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.api.deps import get_market_provider
from app.market_data.contracts import DataQuality, DataResult, Quote

CHINA = ZoneInfo("Asia/Shanghai")


class FakeProvider:
    source = "测试行情"

    def __init__(self) -> None:
        self.now = datetime.now(CHINA)

    def get_quote(self, symbol: str) -> DataResult[Quote]:
        return DataResult(
            value=Quote(symbol=symbol, name="浦发银行", last=Decimal("10.50")),
            source=self.source,
            fetched_at=self.now,
            observed_at=self.now,
            quality=DataQuality.FRESH,
        )

    def get_bars(self, symbol: str, timeframe: object) -> DataResult[tuple]:
        raise AssertionError("本测试不读取K线")

    def get_security(self, symbol: str) -> DataResult[object]:
        raise AssertionError("本测试不读取证券元数据")


def test_quote_with_injected_provider(api_client: TestClient) -> None:
    api_client.app.dependency_overrides[get_market_provider] = lambda: FakeProvider()
    try:
        response = api_client.get("/market/quote/600000")
    finally:
        api_client.app.dependency_overrides.pop(get_market_provider, None)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["source"] == "测试行情"
    assert payload["quality"] == "FRESH"
    assert payload["value"]["symbol"] == "600000"
    assert payload["value"]["last"] == "10.50"
    assert payload["fetched_at"].endswith("+08:00")
