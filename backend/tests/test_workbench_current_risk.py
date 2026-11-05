"""M8 §15.64 current-risk calculations are not broker or quote certification."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.workbench.current_risk import (
    PositionRiskFacts,
    account_current_risk,
    position_current_risk,
)

NOW = datetime(2026, 10, 29, 0, tzinfo=UTC)


def _position(**changes):
    data = {
        "symbol": "600000",
        "current_price": Decimal("10.30"),
        "price_source": "trusted-price-adapter",
        "price_as_of": NOW - timedelta(minutes=1),
        "price_current_verified": True,
        "core_quantity": Decimal(100),
        "core_stop": Decimal("9.50"),
        "t_quantity": Decimal(20),
        "t_stop": Decimal("10.00"),
    }
    data.update(changes)
    return PositionRiskFacts(**data)


def _account(positions, **changes):
    args = {
        "equity": Decimal(10000),
        "equity_source": "trusted-account-adapter",
        "equity_as_of": NOW - timedelta(minutes=1),
        "equity_verified": True,
        "complete_holdings": True,
        "now": NOW,
    }
    args.update(changes)
    return account_current_risk(positions, **args)


def test_core_and_t_stops_are_independent_with_exact_decimal_risk():
    risk = position_current_risk(_position(), now=NOW)
    assert risk.status == "available"
    assert risk.core_amount == Decimal("80.00")
    assert risk.t_amount == Decimal("6.00")
    assert risk.amount == Decimal("86.00")
    assert risk.percent is None


def test_no_t_position_needs_no_t_stop_but_live_t_position_does():
    core_only = position_current_risk(
        _position(t_quantity=Decimal(0), t_stop=None), now=NOW,
    )
    assert core_only.status == "available"
    assert core_only.t_amount == 0
    assert position_current_risk(_position(t_stop=None), now=NOW).status == "unavailable"


def test_unverified_or_undated_current_quote_cannot_create_risk():
    cases = [
        {"price_current_verified": False},
        {"price_source": " "},
        {"price_as_of": None},
        {"price_as_of": NOW.replace(tzinfo=None)},
        {"price_as_of": NOW + timedelta(seconds=1)},
        {"current_price": None},
        {"current_price": Decimal("NaN")},
        {"current_price": Decimal("Infinity")},
        {"current_price": Decimal(-1)},
    ]
    for case in cases:
        result = position_current_risk(_position(**case), now=NOW)
        assert result.status == "unavailable"
        assert result.amount is None


def test_missing_invalid_or_negative_bucket_values_fail_closed():
    for case in [
        {"core_quantity": None},
        {"core_quantity": Decimal(-1)},
        {"core_quantity": Decimal("NaN")},
        {"t_quantity": None},
        {"t_quantity": Decimal("Infinity")},
        {"core_stop": None},
        {"core_stop": Decimal("NaN")},
        {"t_stop": Decimal(0)},
        {"t_stop": Decimal(-1)},
        {"core_quantity": Decimal(0), "t_quantity": Decimal(0)},
    ]:
        assert position_current_risk(_position(**case), now=NOW).status == "unavailable"


def test_price_below_either_stop_requires_review_not_negative_risk():
    for case in [
        {"current_price": Decimal("9.40")},
        {"t_stop": Decimal("10.50")},
    ]:
        result = position_current_risk(_position(**case), now=NOW)
        assert result.status == "crossed"
        assert result.amount is None
        assert "穿越" in result.warning
    at_stop = position_current_risk(
        _position(current_price=Decimal(10), t_stop=Decimal(10)), now=NOW,
    )
    assert at_stop.status == "available"
    assert at_stop.t_amount == 0


def test_account_risk_requires_complete_holdings_and_trusted_equity():
    positions = [_position()]
    for case in [
        {"complete_holdings": False},
        {"equity_verified": False},
        {"equity_source": None},
        {"equity_as_of": None},
        {"equity_as_of": NOW + timedelta(minutes=1)},
        {"equity": Decimal(0)},
        {"equity": Decimal("NaN")},
    ]:
        result = _account(positions, **case)
        assert result.status == "unavailable"
        assert result.amount is None
    assert _account([]).status == "unavailable"
    assert _account([_position(), _position()]).status == "unavailable"


def test_account_aggregates_only_complete_current_risk_without_3_percent_gate():
    # The confirmed §15.63 rule is display-only even above 3% total risk.
    second = _position(
        symbol="000001", current_price=Decimal(20),
        core_quantity=Decimal(200), core_stop=Decimal(10),
        t_quantity=Decimal(0), t_stop=None,
    )
    result = _account([_position(), second], equity=Decimal(1000))
    assert result.status == "available"
    assert result.amount == Decimal(2086)
    assert result.percent == Decimal("208.6")
    assert "不新增账户级" in result.warning

    incomplete = _account([_position(), _position(
        symbol="000001", price_current_verified=False,
    )])
    assert incomplete.status == "unavailable"
    crossed = _account([_position(), _position(
        symbol="000001", t_stop=Decimal("10.50"),
    )])
    assert crossed.status == "crossed"
    assert crossed.amount is None
