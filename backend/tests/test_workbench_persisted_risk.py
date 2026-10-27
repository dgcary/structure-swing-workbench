"""M8 historical risk projections require dated, complete CORE-only evidence."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.domain.enums import PlanVersionState, PositionBucketType
from app.workbench.overview import build_overview
from app.workbench.persisted import _core_only_risk, project_persisted

AT = datetime(2026, 10, 27, 9, 30, tzinfo=UTC)


class _ReadOnlySession:
    """Return explicit persisted rows; no database dialect may fabricate a timezone."""

    def __init__(self, snapshot, position, buckets, version, plan):
        self.snapshot = snapshot
        self.versions = [(version, plan)] if version is not None else []
        # positions, their two buckets, then open actions and plan audits.
        self.rows = iter([[position], buckets] + ([[], []] if version is not None else []))

    def scalar(self, _statement):
        return self.snapshot

    def scalars(self, _statement):
        return iter(next(self.rows))

    def execute(self, _statement):
        return self.versions


def _projection(*, core="100", t="0", cost="10", stop="9",
                snapshot_at=AT, version_at=AT - timedelta(hours=1),
                with_plan=True, buckets_complete=True):
    snapshot = SimpleNamespace(
        id="snapshot-1", captured_at=snapshot_at, source="manual",
        total_equity=Decimal("200000"), available_cash=Decimal("100000"),
    )
    position = SimpleNamespace(
        id="position-1", instrument_code="600000",
        total_quantity=Decimal("100"), market_value=Decimal("1200"),
        broker_cost_price=Decimal("10"),
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
        updated_at=version_at,
        structure_invalidation_price=Decimal(stop) if stop is not None else None,
        first_target_price=Decimal("12"),
    ) if with_plan else None
    plan = SimpleNamespace(
        instrument_code="600000", instrument_name="人工指定标的",
    )
    return build_overview(persisted=project_persisted(
        _ReadOnlySession(snapshot, position, buckets, version, plan)
    ))


def _metric(overview, key):
    return next(row for row in overview["metrics"] if row["key"] == key)


def test_sourced_core_only_risk_is_historical_not_trade_permission():
    overview = _projection()
    risk = _metric(overview, "account_risk")
    assert risk["status"] == "available"
    assert Decimal(risk["value"]) == Decimal("0.05")
    assert "账户快照/" in risk["source"] and "有效计划止损" in risk["source"]
    assert risk["as_of"] == AT.isoformat()
    plan = overview["effective_plans"][0]
    assert Decimal(plan["current_risk"]) == Decimal("100")
    assert plan["initial_risk"] is None
    assert "历史快照" in plan["warning"]
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
    assert overview["trade_execution_enabled"] is False


def test_invalid_numeric_core_risk_fails_closed():
    for quantity, cost, stop in [
        (Decimal("0"), Decimal("10"), Decimal("9")),
        (Decimal("NaN"), Decimal("10"), Decimal("9")),
        (Decimal("100"), Decimal("Infinity"), Decimal("9")),
        (Decimal("100"), Decimal("10"), Decimal("NaN")),
        (Decimal("100"), Decimal("10"), Decimal("10")),
    ]:
        assert _core_only_risk(quantity, cost, stop) is None
