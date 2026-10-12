"""Explicit suspension and delisting flags must be sourced, not guessed."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

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
        return Rows([
            {"item": key, "value": value}
            for key, value in self.details.items()
        ])


@pytest.mark.parametrize("details,expected", [
    ({"是否停牌": "是", "退市风险警示": "有"}, (True, True)),
    ({"停牌状态": "正常交易", "是否退市风险警示": "否"}, (False, False)),
    ({"是否停牌": None, "退市风险警示": "--"}, (None, None)),
    ({"停牌状态": "未识别状态", "退市风险警示": "待核实"}, (None, None)),
    ({"是否停牌": "是", "停牌状态": "待核实", "退市风险警示": "无"}, (None, False)),
    ({"是否停牌": "否", "是否退市风险警示": "有", "退市风险警示": "待核实"}, (False, None)),
])
def test_only_explicit_status_values_are_mapped(details, expected):
    result = AKShareProvider(
        client=Client(details), clock=lambda: NOW
    ).get_security("600000")
    assert result.quality is DataQuality.UNVERIFIED
    assert (result.value.suspended, result.value.delisting_risk) == expected
    for field, value in zip(("suspended", "delisting_risk"), expected):
        assert (field in result.missing_fields) is (value is None)


def test_conflicting_status_values_are_error_not_arbitrarily_resolved():
    result = AKShareProvider(client=Client({
        "是否停牌": "是", "停牌状态": "正常交易",
        "退市风险警示": "无",
    }), clock=lambda: NOW).get_security("600000")
    assert result.quality is DataQuality.ERROR
    assert result.value.suspended is None
    assert result.value.delisting_risk is None
    assert "conflicting source status fields" in result.error


def test_quote_does_not_infer_suspension_from_zero_volume():
    client = Client({})
    result = AKShareProvider(client=client, clock=lambda: NOW).get_security(
        "600000"
    )
    assert result.value.suspended is None
    assert result.value.delisting_risk is None
