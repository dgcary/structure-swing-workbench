"""M4 metadata normalization: missing source markers never become facts."""
from datetime import datetime
from zoneinfo import ZoneInfo

from app.market_data.akshare_adapter import AKShareProvider
from app.market_data.contracts import DataQuality

NOW = datetime(2026, 10, 9, 14, 30, tzinfo=ZoneInfo("Asia/Shanghai"))


class Rows:
    def __init__(self, records):
        self.records = records

    def to_dict(self, orient):
        assert orient == "records"
        return self.records


class Client:
    def __init__(self, details):
        self.details = details

    def stock_zh_a_spot_em(self):
        return Rows([{
            "代码": "600000", "名称": "浦发银行", "最新价": 10,
            "今开": 10, "最高": 10, "最低": 10,
            "更新时间": "2026-10-09 14:29:00",
        }])

    def stock_individual_info_em(self, **kwargs):
        assert kwargs["symbol"] == "600000"
        return Rows([{"item": key, "value": value} for key, value in self.details.items()])


def test_missing_industry_and_primary_exchange_use_known_fallback():
    result = AKShareProvider(client=Client({
        "行业": float("nan"), "交易所": "--",
        "上市交易所": "上海证券交易所",
    }), clock=lambda: NOW).get_security("600000")
    assert result.quality is DataQuality.FRESH
    assert result.value.industry is None
    assert result.value.exchange == "上海证券交易所"
    assert "industry" in result.missing_fields
    assert "exchange" not in result.missing_fields


def test_missing_exchange_metadata_is_not_serialized_as_placeholder():
    result = AKShareProvider(client=Client({
        "行业": "银行", "交易所": "NaN", "上市交易所": "-",
    }), clock=lambda: NOW).get_security("600000")
    assert result.quality is DataQuality.FRESH
    assert result.value.industry == "银行"
    assert result.value.exchange is None
    assert "exchange" in result.missing_fields
