"""Historical CORE cost estimates must never impersonate current market risk."""

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal, localcontext
from types import SimpleNamespace

import pytest

from app.db.models import PositionBucketSnapshot, PositionSnapshot
from app.domain.enums import PlanVersionState, PositionBucketType
from app.workbench.overview import build_overview
from app.workbench.persisted import _core_only_risk, project_persisted

AT = datetime.now(UTC) - timedelta(hours=1)


class _ReadOnlySession:
    """Return explicit persisted rows; no database dialect may fabricate a timezone."""

    def __init__(self, snapshot, position, buckets, version, plan, zero_conflict=False):
        self.snapshot = snapshot
        self.versions = [(version, plan)] if version is not None else []
        self.position = position
        self.buckets = buckets
        self.zero_conflict = zero_conflict
        self.bucket_reads = 0

    def scalar(self, _statement):
        return self.snapshot

    def scalars(self, statement):
        entity = statement.column_descriptions[0]["entity"]
        if entity is PositionSnapshot:
            if self.zero_conflict:
                zero_position = SimpleNamespace(
                    id="position-zero", instrument_code="600001",
                    total_quantity=Decimal(0), market_value=Decimal(0),
                    broker_cost_price=Decimal(0),
                )
                return iter([self.position, zero_position])
            return iter([self.position])
        if entity is PositionBucketSnapshot:
            self.bucket_reads += 1
            if self.zero_conflict and self.bucket_reads == 2:
                return iter([SimpleNamespace(
                    bucket_type=PositionBucketType.CORE,
                    quantity=Decimal(1), strategy_cost_price=Decimal(10),
                )])
            return iter(self.buckets)
        return iter([])

    def execute(self, _statement):
        return self.versions


def _projection(*, core="100", t="0", cost="10", stop="9",
                quantity="100", equity="200000", market_value="1200", available_cash="100000",
                snapshot_at=AT, version_at=AT - timedelta(hours=1),
                with_plan=True, buckets_complete=True, zero_conflict=False,
                valid_until=None, additional_version_stop=None,
                additional_version_valid_until=None, snapshot_source="manual"):
    snapshot = SimpleNamespace(
        id="snapshot-1", captured_at=snapshot_at, source=snapshot_source,
        total_equity=Decimal(equity), available_cash=Decimal(available_cash),
    )
    position = SimpleNamespace(
        id="position-1", instrument_code="600000",
        total_quantity=Decimal(quantity),
        market_value=Decimal(market_value) if market_value is not None else None,
        broker_cost_price=Decimal(10),
    )
    buckets = [
        SimpleNamespace(
            bucket_type=PositionBucketType.CORE,
            quantity=Decimal(core),
            strategy_cost_price=Decimal(cost) if cost is not None else None,
        ),
    ]
    if buckets_complete:
        buckets.append(SimpleNamespace(
            bucket_type=PositionBucketType.T,
            quantity=Decimal(t), strategy_cost_price=None,
        ))
    version = SimpleNamespace(
        id="version-1", version_number=1, state=PlanVersionState.EFFECTIVE,
        updated_at=version_at, valid_until=valid_until,
        structure_invalidation_price=Decimal(stop) if stop is not None else None,
        first_target_price=Decimal(12),
    ) if with_plan else None
    plan = SimpleNamespace(
        instrument_code="600000", instrument_name="人工指定标的",
    )
    session = _ReadOnlySession(
        snapshot, position, buckets, version, plan, zero_conflict=zero_conflict
    )
    if additional_version_stop is not None:
        session.versions.append((
            SimpleNamespace(
                id="version-2", version_number=2, state=PlanVersionState.EFFECTIVE,
                updated_at=version_at,
                valid_until=additional_version_valid_until,
                structure_invalidation_price=Decimal(additional_version_stop),
                first_target_price=Decimal(12),
            ),
            plan,
        ))
    return build_overview(persisted=project_persisted(session))


def _metric(overview, key):
    return next(row for row in overview["metrics"] if row["key"] == key)


def test_sourced_core_only_risk_is_historical_not_trade_permission():
    overview = _projection()
    risk = _metric(overview, "account_risk")
    assert risk["status"] == "unavailable"
    assert risk["value"] is None and risk["source"] is None
    plan = overview["effective_plans"][0]
    assert plan["current_risk"] is None
    assert plan["initial_risk"] is None
    assert Decimal(plan["historical_cost_risk_estimate"]) == Decimal(100)
    assert "缺可信当前市价" in plan["warning"]
    assert "账户快照/" in plan["source"]
    assert overview["trade_execution_enabled"] is False
    assert overview["pending_actions"] == []


@pytest.mark.parametrize("kwargs", [
    {"core": "70", "t": "30"},  # T stop is not persisted: never omit T exposure.
    {"cost": None},  # Broker cost must not replace missing strategy cost.
    {"stop": None},
    {"stop": "10"},  # A stop above the cost is not proof of zero risk.
    {"version_at": AT + timedelta(minutes=1)},  # Newer plan vs old snapshot.
    {"snapshot_at": AT.replace(tzinfo=None)},  # SQLite-naive timestamp.
    {"with_plan": False},
    {"buckets_complete": False},
    {"quantity": "NaN"},
    {"equity": "NaN"},
    {"core": "NaN"},
])
def test_missing_or_mismatched_risk_facts_remain_unknown(kwargs):
    overview = _projection(**kwargs)
    risk = _metric(overview, "account_risk")
    assert risk["status"] == "unavailable"
    assert risk["value"] is None
    assert risk["source"] is None
    assert risk["as_of"] is None
    for plan in overview["effective_plans"]:
        assert plan["current_risk"] is None
        if kwargs.get("equity") == "NaN":
            # A historical cost estimate may be displayed separately, but
            # cannot certify initial or current risk.
            assert Decimal(plan["historical_cost_risk_estimate"]) == Decimal(100)
    assert overview["trade_execution_enabled"] is False


def test_large_valid_core_risk_keeps_fractional_yuan_in_persisted_projection():
    # A NUMERIC(20,4) quantity times a NUMERIC(18,4) stop distance can
    # require 38 significant digits. Never silently round a sourced risk fact.
    quantity = "9999999999999999.9999"
    cost = "99999999999999.9999"
    stop = "0.0001"
    exact = "999999999999999997990000000000.00000002"
    assert str(_core_only_risk(
        Decimal(quantity), Decimal(cost), Decimal(stop)
    )) == exact

    overview = _projection(
        quantity=quantity, core=quantity, cost=cost, stop=stop,
        equity="9999999999999999.9999",
    )
    plan = overview["effective_plans"][0]
    assert plan["current_risk"] is None
    assert plan["historical_cost_risk_estimate"] == exact
    assert "缺可信当前市价" in plan["warning"]
    account_risk = _metric(overview, "account_risk")
    assert account_risk["status"] == "unavailable"
    assert account_risk["value"] is None
    assert overview["trade_execution_enabled"] is False


def test_persisted_account_ratios_preserve_full_numeric_precision():
    # Exact M1 NUMERIC bounds can require >28 digits during aggregation and
    # division. The historical estimate must not silently round before display.
    quantity = Decimal("9999999999999999.9999")
    cost = Decimal("99999999999999.9999")
    stop = Decimal("0.0001")
    equity = Decimal("7777777777777777.7777")
    with localcontext() as context:
        context.prec = 64
        expected_position_pct = Decimal(1200) * Decimal(100) / equity

    overview = _projection(
        quantity=str(quantity), core=str(quantity), cost=str(cost),
        stop=str(stop), equity=str(equity),
    )
    assert _metric(overview, "account_risk")["status"] == "unavailable"
    with localcontext() as context:
        context.prec = 64
        historical = quantity * (cost - stop)
    assert overview["effective_plans"][0]["historical_cost_risk_estimate"] == str(historical)
    assert _metric(overview, "position_ratio")["value"] == str(expected_position_pct)
    assert overview["trade_execution_enabled"] is False


def test_invalid_numeric_core_risk_fails_closed():
    for quantity, cost, stop in [
        (Decimal(0), Decimal(10), Decimal(9)),
        (Decimal("NaN"), Decimal(10), Decimal(9)),
        (Decimal(100), Decimal("Infinity"), Decimal(9)),
        (Decimal(100), Decimal(10), Decimal("NaN")),
        (Decimal(100), Decimal(10), Decimal(10)),
    ]:
        assert _core_only_risk(quantity, cost, stop) is None


def test_zero_quantity_with_conflicting_buckets_blocks_total_risk():
    # A zero-share position can still carry corrupt allocations; a partial
    # inventory must never produce an apparently complete account-risk figure.
    overview = _projection(zero_conflict=True)
    risk = _metric(overview, "account_risk")
    assert risk["status"] == "unavailable"
    assert risk["value"] is None
    assert overview["trade_execution_enabled"] is False


def test_expired_effective_flag_does_not_publish_an_active_plan_or_risk():
    # The plan's explicit validity date wins over a stale is_effective flag.
    market_today = datetime.now(timezone(timedelta(hours=8))).date()
    expired = _projection(valid_until=market_today - timedelta(days=1))
    assert expired["effective_plans"] == []
    assert expired["pending_actions"] == []
    assert expired["audit_results"] == []
    assert _metric(expired, "account_risk")["status"] == "unavailable"
    assert expired["trade_execution_enabled"] is False

    still_valid = _projection(valid_until=market_today)
    assert len(still_valid["effective_plans"]) == 1
    assert _metric(still_valid, "account_risk")["status"] == "unavailable"
    assert still_valid["effective_plans"][0]["historical_cost_risk_estimate"] == "100"


def test_future_dated_snapshot_and_plan_do_not_authenticate_account_risk():
    # Clock errors and predated records must not look like observed account facts.
    future = datetime.now(UTC) + timedelta(days=1)
    snapshot = _projection(snapshot_at=future)
    assert snapshot["holdings"] is None
    assert _metric(snapshot, "equity")["status"] == "unavailable"
    assert _metric(snapshot, "account_risk")["status"] == "unavailable"
    assert snapshot["trade_execution_enabled"] is False

    plan = _projection(version_at=future)
    assert _metric(plan, "account_risk")["status"] == "unavailable"
    assert plan["effective_plans"] == []
    assert plan["pending_actions"] == []
    assert plan["audit_results"] == []
    assert plan["trade_execution_enabled"] is False

@pytest.mark.parametrize("other_stop", ["9", "8"])
def test_two_effective_plans_for_one_symbol_block_account_risk(other_stop):
    # A single aggregate CORE position cannot be assigned to either plan's
    # stop without an independently verified per-plan inventory allocation.
    overview = _projection(additional_version_stop=other_stop)
    assert len(overview["effective_plans"]) == 2
    assert all(plan["current_risk"] is None for plan in overview["effective_plans"])
    assert all(plan["historical_cost_risk_estimate"] is None for plan in overview["effective_plans"])
    assert all("多份有效计划" in plan["warning"] for plan in overview["effective_plans"])
    risk = _metric(overview, "account_risk")
    assert risk["status"] == "unavailable"
    assert risk["value"] is None
    assert risk["source"] is None
    assert overview["trade_execution_enabled"] is False


def test_expired_second_plan_does_not_invalidate_unique_current_risk():
    market_today = datetime.now(timezone(timedelta(hours=8))).date()
    overview = _projection(
        additional_version_stop="8",
        additional_version_valid_until=market_today - timedelta(days=1),
    )
    assert len(overview["effective_plans"]) == 1
    assert overview["effective_plans"][0]["current_risk"] is None
    assert overview["effective_plans"][0]["historical_cost_risk_estimate"] == "100"
    assert _metric(overview, "account_risk")["status"] == "unavailable"
    assert overview["trade_execution_enabled"] is False

@pytest.mark.parametrize("source", ["", " ", "\t"])
def test_blank_snapshot_source_cannot_authenticate_account_facts(source):
    overview = _projection(snapshot_source=source)
    for key in ("equity", "available_cash", "position_count", "account_risk"):
        metric = _metric(overview, key)
        assert metric["status"] == "unavailable"
        assert metric["value"] is None
        assert metric["source"] is None
    assert overview["holdings"] is None
    assert overview["trade_execution_enabled"] is False


def test_market_value_is_not_a_verified_current_quote():
    # Snapshot market_value (1200 / 100 shares) may imply a price of 12,
    # but lacks independent quote provenance/time and CORE/T stop completeness.
    overview = _projection()
    plan = overview["effective_plans"][0]
    assert plan["historical_cost_risk_estimate"] == "100"
    assert plan["initial_risk"] is None
    assert plan["current_risk"] is None
    assert _metric(overview, "account_risk")["status"] == "unavailable"
    assert overview["trade_execution_enabled"] is False


@pytest.mark.parametrize(("market_value", "expected_pct"), [
    ("900", "90"),
    ("1000", "100"),
    ("1200", "120"),
    ("1500", "150"),
])
def test_gross_exposure_snapshot_does_not_hide_over_100_percent(market_value, expected_pct):
    # §15.48: over-limit gross exposure must remain visible for review.
    # A sourced historical snapshot is not an execution authorization.
    overview = _projection(
        equity="1000", available_cash="0", market_value=market_value,
    )
    ratio = _metric(overview, "position_ratio")
    assert ratio["status"] == "available"
    assert Decimal(ratio["value"]) == Decimal(expected_pct)
    assert "持仓市值" in ratio["source"]
    assert ratio["as_of"] is not None
    assert _metric(overview, "account_risk")["status"] == "unavailable"
    assert overview["trade_execution_enabled"] is False


@pytest.mark.parametrize("market_value", [None, "-1", "NaN"])
def test_invalid_snapshot_market_value_cannot_publish_exposure(market_value):
    overview = _projection(equity="1000", available_cash="0", market_value=market_value)
    ratio = _metric(overview, "position_ratio")
    assert ratio["status"] == "unavailable"
    assert ratio["value"] is None
    assert overview["trade_execution_enabled"] is False
