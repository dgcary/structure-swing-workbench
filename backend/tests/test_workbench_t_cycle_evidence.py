"""M8 T-cycle evidence is sourced from fills, never from action drafts."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from app.domain.enums import ActionType, OrderSide
from app.workbench.t_cycle_evidence import recorded_t_cycles

NOW = datetime(2026, 10, 27, 12, tzinfo=UTC)
DAY = date(2026, 10, 27)


def _fill(
    identifier, side, qty, hour, *, source="manual", at=None, price="10", external_id=None
):
    return SimpleNamespace(
        id=identifier, side=side, quantity=Decimal(qty), source=source,
        price=Decimal(price) if price is not None else None,
        executed_at=at if at is not None else NOW.replace(hour=hour),
        external_execution_id=external_id,
    )


def _record(action_type, fill, *, key="cycle-1", symbol="600000"):
    return (symbol, key, action_type, fill)


def test_recorded_split_positive_t_closes_once_with_explicit_fill_sources():
    rows = [
        _record(ActionType.POSITIVE_T_SELL, _fill("sell-1", OrderSide.SELL, "30", 1)),
        _record(ActionType.POSITIVE_T_SELL, _fill("sell-2", OrderSide.SELL, "70", 2)),
        _record(ActionType.POSITIVE_T_BUYBACK, _fill("buy-1", OrderSide.BUY, "40", 3)),
        _record(ActionType.POSITIVE_T_BUYBACK, _fill("buy-2", OrderSide.BUY, "60", 4)),
    ]
    result = recorded_t_cycles(rows, DAY, now=NOW)
    assert len(result) == 1
    cycle = result[0]
    assert cycle["state"] == "closed"
    assert cycle["direction"] == "positive"
    assert cycle["opening_quantity"] == "100"
    assert cycle["closing_quantity"] == "100"
    assert len(cycle["sources"]) == 4
    assert cycle["broker_reconciled"] is False
    assert cycle["trade_execution_enabled"] is False


def test_partial_reverse_t_is_open_not_a_completed_cycle():
    rows = [
        _record(ActionType.REVERSE_T_BUY, _fill("buy", OrderSide.BUY, "100", 1)),
        _record(ActionType.REVERSE_T_SELL, _fill("sell", OrderSide.SELL, "40", 2)),
    ]
    cycle = recorded_t_cycles(rows, DAY, now=NOW)[0]
    assert cycle["state"] == "open"
    assert cycle["direction"] == "reverse"
    assert cycle["opening_quantity"] == "100"
    assert cycle["closing_quantity"] == "40"


def test_missing_key_wrong_side_and_overfilled_close_are_conflicts():
    cases = [
        [_record(ActionType.POSITIVE_T_SELL,
                 _fill("missing", OrderSide.SELL, "10", 1), key=None)],
        [_record(ActionType.POSITIVE_T_SELL,
                 _fill("wrong", OrderSide.BUY, "10", 1))],
        [
            _record(ActionType.REVERSE_T_BUY, _fill("open", OrderSide.BUY, "10", 1)),
            _record(ActionType.REVERSE_T_SELL, _fill("close", OrderSide.SELL, "11", 2)),
        ],
        [_record(ActionType.REVERSE_T_SELL,
                 _fill("no-open", OrderSide.SELL, "10", 2))],
    ]
    for rows in cases:
        cycle = recorded_t_cycles(rows, DAY, now=NOW)[0]
        assert cycle["state"] == "conflict"
        assert cycle["opening_quantity"] is None
        assert cycle["broker_reconciled"] is False


def test_cross_day_close_and_close_before_open_never_count():
    prior_day = NOW - timedelta(days=1)
    cross_day = [
        _record(ActionType.POSITIVE_T_SELL, _fill(
            "yesterday", OrderSide.SELL, "10", 1, at=prior_day)),
        _record(ActionType.POSITIVE_T_BUYBACK,
                _fill("today", OrderSide.BUY, "10", 2)),
    ]
    reverse_order = [
        _record(ActionType.POSITIVE_T_BUYBACK, _fill("early", OrderSide.BUY, "10", 1)),
        _record(ActionType.POSITIVE_T_SELL, _fill("late", OrderSide.SELL, "10", 2)),
    ]
    for rows in (cross_day, reverse_order):
        assert recorded_t_cycles(rows, DAY, now=NOW)[0]["state"] == "conflict"


def test_future_and_timezone_naive_fills_fail_closed():
    for timestamp in [NOW + timedelta(days=1), NOW.replace(tzinfo=None)]:
        rows = [
            _record(ActionType.POSITIVE_T_SELL,
                    _fill("open", OrderSide.SELL, "10", 1)),
            _record(ActionType.POSITIVE_T_BUYBACK,
                    _fill("close", OrderSide.BUY, "10", 2, at=timestamp)),
        ]
        assert recorded_t_cycles(rows, DAY, now=NOW)[0]["state"] == "conflict"


def test_empty_or_other_day_records_do_not_fabricate_zero_today():
    assert recorded_t_cycles([], DAY, now=NOW) == []
    other_day = _record(
        ActionType.REVERSE_T_BUY,
        _fill("old", OrderSide.BUY, "10", 1, at=NOW - timedelta(days=2)),
    )
    assert recorded_t_cycles([other_day], DAY, now=NOW) == []


def test_early_close_cannot_be_covered_by_later_opening_fills():
    rows = [
        _record(ActionType.POSITIVE_T_SELL, _fill("open-10", OrderSide.SELL, "10", 1)),
        _record(ActionType.POSITIVE_T_BUYBACK, _fill("close-100", OrderSide.BUY, "100", 2)),
        _record(ActionType.POSITIVE_T_SELL, _fill("late-open-90", OrderSide.SELL, "90", 3)),
    ]
    cycle = recorded_t_cycles(rows, DAY, now=NOW)[0]
    assert cycle["state"] == "conflict"


def test_simultaneous_open_close_without_ordering_evidence_fails_closed():
    rows = [
        _record(ActionType.REVERSE_T_BUY, _fill("buy", OrderSide.BUY, "10", 1)),
        _record(ActionType.REVERSE_T_SELL, _fill("sell", OrderSide.SELL, "10", 1)),
    ]
    assert recorded_t_cycles(rows, DAY, now=NOW)[0]["state"] == "conflict"


def test_same_symbol_and_key_across_plan_versions_cannot_close_each_other():
    """Independent plan versions must not manufacture a completed T cycle."""
    opening = _fill("open-a", OrderSide.SELL, "100", 1)
    closing = _fill("close-b", OrderSide.BUY, "100", 2)
    opening.action = SimpleNamespace(plan_version_id="version-a")
    closing.action = SimpleNamespace(plan_version_id="version-b")
    cycles = recorded_t_cycles([
        _record(ActionType.POSITIVE_T_SELL, opening, key="reused-key"),
        _record(ActionType.POSITIVE_T_BUYBACK, closing, key="reused-key"),
    ], DAY, now=NOW)
    assert len(cycles) == 2
    assert {row["plan_version_id"] for row in cycles} == {"version-a", "version-b"}
    assert {row["state"] for row in cycles} == {"open", "conflict"}
    assert all(row["state"] != "closed" for row in cycles)


def test_unkeyed_fill_does_not_collide_with_user_key_matching_old_prefix():
    """A legitimate key starting with 'unkeyed:' must not absorb a missing key."""
    keyed = _fill("sell", OrderSide.SELL, "10", 1)
    unkeyed = _fill("42", OrderSide.BUY, "10", 2)
    cycles = recorded_t_cycles([
        _record(ActionType.POSITIVE_T_SELL, keyed, key="unkeyed:42"),
        _record(ActionType.POSITIVE_T_BUYBACK, unkeyed, key=None),
    ], DAY, now=NOW)
    assert len(cycles) == 2
    assert {row["cycle_key"] for row in cycles} == {"unkeyed:42", None}
    assert all(row["state"] != "closed" for row in cycles)


def test_nonfinite_or_nonpositive_fill_quantity_fails_closed_without_crashing():
    """Malformed persisted NUMERIC values must not make the overview return 500."""
    for bad_quantity in ("NaN", "Infinity", "-Infinity", "-1", "0"):
        rows = [
            _record(ActionType.POSITIVE_T_SELL,
                    _fill("valid-open", OrderSide.SELL, "10", 1)),
            _record(ActionType.POSITIVE_T_BUYBACK,
                    _fill("invalid-close", OrderSide.BUY, bad_quantity, 2)),
        ]
        cycle = recorded_t_cycles(rows, DAY, now=NOW)[0]
        assert cycle["state"] == "conflict"
        assert cycle["opening_quantity"] is None
        assert cycle["closing_quantity"] is None
        assert cycle["broker_reconciled"] is False


def test_missing_fill_source_fails_closed_without_crashing():
    rows = [
        _record(ActionType.REVERSE_T_BUY,
                _fill("missing-source", OrderSide.BUY, "10", 1, source=None)),
    ]
    cycle = recorded_t_cycles(rows, DAY, now=NOW)[0]
    assert cycle["state"] == "conflict"
    assert cycle["trade_execution_enabled"] is False


def test_invalid_execution_price_never_certifies_a_completed_t_cycle():
    """NUMERIC NaN, infinity, zero, negative or missing prices are not fill evidence."""
    for invalid in ("NaN", "Infinity", "-Infinity", "0", "-1", None):
        rows = [
            _record(ActionType.POSITIVE_T_SELL,
                    _fill("open", OrderSide.SELL, "10", 1, price=invalid)),
            _record(ActionType.POSITIVE_T_BUYBACK,
                    _fill("close", OrderSide.BUY, "10", 2)),
        ]
        cycle = recorded_t_cycles(rows, DAY, now=NOW)[0]
        assert cycle["state"] == "conflict"
        assert cycle["opening_quantity"] is None
        assert cycle["closing_quantity"] is None
        assert cycle["broker_reconciled"] is False
        assert cycle["trade_execution_enabled"] is False

        # Invalid closing-leg prices must fail closed as well.
        rows[0] = _record(
            ActionType.POSITIVE_T_SELL, _fill("open", OrderSide.SELL, "10", 1)
        )
        rows[1] = _record(
            ActionType.POSITIVE_T_BUYBACK,
            _fill("close", OrderSide.BUY, "10", 2, price=invalid),
        )
        assert recorded_t_cycles(rows, DAY, now=NOW)[0]["state"] == "conflict"


def test_duplicate_broker_execution_reference_never_closes_a_cycle():
    """Two local fill IDs cannot stand in for two distinct broker executions."""
    rows = [
        _record(ActionType.POSITIVE_T_SELL, _fill(
            "open-1", OrderSide.SELL, "10", 1,
            source="broker-csv", external_id="order-123")),
        _record(ActionType.POSITIVE_T_SELL, _fill(
            "open-2", OrderSide.SELL, "10", 2,
            source="broker-csv", external_id="order-123")),
        _record(ActionType.POSITIVE_T_BUYBACK, _fill(
            "close", OrderSide.BUY, "20", 3,
            source="broker-csv", external_id="order-456")),
    ]
    cycle = recorded_t_cycles(rows, DAY, now=NOW)[0]
    assert cycle["state"] == "conflict"
    assert cycle["opening_quantity"] is None
    assert cycle["broker_reconciled"] is False
    assert cycle["trade_execution_enabled"] is False


def test_duplicate_external_reference_across_plan_versions_taints_both_cycles():
    """A broker reference reused across plans cannot certify either cycle."""
    a_open = _fill(
        "a-open", OrderSide.SELL, "10", 1, source="broker-csv", external_id="shared"
    )
    a_close = _fill(
        "a-close", OrderSide.BUY, "10", 2, source="broker-csv", external_id="a-close"
    )
    b_open = _fill(
        "b-open", OrderSide.SELL, "10", 3, source="broker-csv", external_id="b-open"
    )
    b_close = _fill(
        "b-close", OrderSide.BUY, "10", 4, source="broker-csv", external_id="shared"
    )
    for fill, version in (
        (a_open, "version-a"), (a_close, "version-a"),
        (b_open, "version-b"), (b_close, "version-b"),
    ):
        fill.action = SimpleNamespace(plan_version_id=version)
    cycles = recorded_t_cycles([
        _record(ActionType.POSITIVE_T_SELL, a_open),
        _record(ActionType.POSITIVE_T_BUYBACK, a_close),
        _record(ActionType.POSITIVE_T_SELL, b_open),
        _record(ActionType.POSITIVE_T_BUYBACK, b_close),
    ], DAY, now=NOW)
    assert len(cycles) == 2
    assert all(cycle["state"] == "conflict" for cycle in cycles)
    assert all(cycle["broker_reconciled"] is False for cycle in cycles)


def test_duplicate_internal_fill_id_cannot_be_double_counted():
    rows = [
        _record(ActionType.REVERSE_T_BUY, _fill("same-id", OrderSide.BUY, "10", 1)),
        _record(ActionType.REVERSE_T_BUY, _fill("same-id", OrderSide.BUY, "10", 2)),
        _record(ActionType.REVERSE_T_SELL, _fill("close", OrderSide.SELL, "20", 3)),
    ]
    cycle = recorded_t_cycles(rows, DAY, now=NOW)[0]
    assert cycle["state"] == "conflict"


def test_broker_reference_is_source_scoped_and_distinct_ids_still_close():
    rows = [
        _record(ActionType.POSITIVE_T_SELL, _fill(
            "open", OrderSide.SELL, "10", 1, source="broker-a", external_id="1")),
        _record(ActionType.POSITIVE_T_BUYBACK, _fill(
            "close", OrderSide.BUY, "10", 2, source="broker-b", external_id="1")),
    ]
    cycle = recorded_t_cycles(rows, DAY, now=NOW)[0]
    assert cycle["state"] == "closed"
    assert cycle["broker_reconciled"] is False


def test_t_execution_reference_reused_by_ordinary_trade_is_conflict():
    """A non-T action must not hide a duplicated broker execution reference."""
    rows = [
        _record(ActionType.POSITIVE_T_SELL, _fill(
            "t-open", OrderSide.SELL, "10", 1,
            source="broker-csv", external_id="same-execution")),
        _record(ActionType.POSITIVE_T_BUYBACK, _fill(
            "t-close", OrderSide.BUY, "10", 2,
            source="broker-csv", external_id="unique-close")),
        _record(ActionType.ORDINARY_ADD, _fill(
            "ordinary", OrderSide.BUY, "10", 3,
            source="broker-csv", external_id="same-execution")),
    ]
    cycles = recorded_t_cycles(rows, DAY, now=NOW)
    assert len(cycles) == 1  # Ordinary actions are never projected as T cycles.
    assert cycles[0]["state"] == "conflict"
    assert cycles[0]["broker_reconciled"] is False
    assert cycles[0]["trade_execution_enabled"] is False


def test_duplicate_internal_fill_id_across_t_and_non_t_is_conflict():
    rows = [
        _record(ActionType.REVERSE_T_BUY, _fill(
            "same-id", OrderSide.BUY, "10", 1)),
        _record(ActionType.REVERSE_T_SELL, _fill(
            "t-close", OrderSide.SELL, "10", 2)),
        _record(ActionType.INITIAL_ENTRY, _fill(
            "same-id", OrderSide.BUY, "10", 3)),
    ]
    cycles = recorded_t_cycles(rows, DAY, now=NOW)
    assert len(cycles) == 1
    assert cycles[0]["state"] == "conflict"


def test_same_external_reference_in_different_sources_does_not_taint_t():
    rows = [
        _record(ActionType.POSITIVE_T_SELL, _fill(
            "t-open", OrderSide.SELL, "10", 1,
            source="broker-a", external_id="123")),
        _record(ActionType.POSITIVE_T_BUYBACK, _fill(
            "t-close", OrderSide.BUY, "10", 2,
            source="broker-a", external_id="456")),
        _record(ActionType.ORDINARY_ADD, _fill(
            "ordinary", OrderSide.BUY, "10", 3,
            source="broker-b", external_id="123")),
    ]
    cycles = recorded_t_cycles(rows, DAY, now=NOW)
    assert len(cycles) == 1
    assert cycles[0]["state"] == "closed"
    assert cycles[0]["broker_reconciled"] is False


def test_unclosed_t_at_day_end_only_exposes_unverified_ordinary_effect():
    """After 15:00 Shanghai, residual first-leg shares need broker reconciliation."""
    positive = [
        _record(ActionType.POSITIVE_T_SELL, _fill("open", OrderSide.SELL, "100", 1)),
        _record(ActionType.POSITIVE_T_BUYBACK, _fill("partial", OrderSide.BUY, "40", 2)),
    ]
    before_close = recorded_t_cycles(
        positive, DAY, now=datetime(2026, 10, 27, 6, tzinfo=UTC)
    )[0]
    assert before_close["state"] == "open"
    assert before_close["end_of_day_unclosed"] is False
    assert before_close["residual_quantity"] is None
    assert before_close["ordinary_effect"] is None
    assert before_close["requires_reaudit"] is False

    after_close = recorded_t_cycles(
        positive, DAY, now=datetime(2026, 10, 27, 7, tzinfo=UTC)
    )[0]
    assert after_close["state"] == "open"  # Not an authenticated BROKEN state.
    assert after_close["end_of_day_unclosed"] is True
    assert after_close["residual_quantity"] == "60"
    assert after_close["ordinary_effect"] == "普通减仓待核验"
    assert after_close["requires_reaudit"] is True
    assert after_close["broker_reconciled"] is False
    assert after_close["trade_execution_enabled"] is False
    assert "未自动转仓" in after_close["warning"]

    reverse = [
        _record(ActionType.REVERSE_T_BUY, _fill("buy", OrderSide.BUY, "100", 1)),
        _record(ActionType.REVERSE_T_SELL, _fill("sell", OrderSide.SELL, "30", 2)),
    ]
    next_day = recorded_t_cycles(
        reverse, DAY, now=datetime(2026, 10, 28, 2, tzinfo=UTC)
    )[0]
    assert next_day["end_of_day_unclosed"] is True
    assert next_day["residual_quantity"] == "70"
    assert next_day["ordinary_effect"] == "普通加仓待核验"
    assert next_day["requires_reaudit"] is True


def test_closed_or_conflicting_t_never_claims_end_of_day_ordinary_conversion():
    closed = [
        _record(ActionType.POSITIVE_T_SELL, _fill("sell", OrderSide.SELL, "10", 1)),
        _record(ActionType.POSITIVE_T_BUYBACK, _fill("buy", OrderSide.BUY, "10", 2)),
    ]
    conflict = [
        _record(ActionType.POSITIVE_T_SELL, _fill("bad", OrderSide.BUY, "10", 1)),
    ]
    for rows, expected in ((closed, "closed"), (conflict, "conflict")):
        cycle = recorded_t_cycles(rows, DAY, now=NOW)[0]
        assert cycle["state"] == expected
        assert cycle["end_of_day_unclosed"] is False
        assert cycle["residual_quantity"] is None
        assert cycle["ordinary_effect"] is None
        assert cycle["requires_reaudit"] is False
        assert cycle["trade_execution_enabled"] is False


def _completed_t_pair(key: str, start_hour: int, *, symbol: str = "600000"):
    return [
        _record(
            ActionType.POSITIVE_T_SELL,
            _fill(f"{symbol}-{key}-open", OrderSide.SELL, "10", start_hour),
            key=key, symbol=symbol,
        ),
        _record(
            ActionType.POSITIVE_T_BUYBACK,
            _fill(f"{symbol}-{key}-close", OrderSide.BUY, "10", start_hour + 1),
            key=key, symbol=symbol,
        ),
    ]


def test_three_recorded_closed_t_cycles_warn_without_claiming_broker_reconciliation():
    """Three independent closed pairs are a lower-bound alert, not a daily total."""
    rows = (
        _completed_t_pair("one", 1)
        + _completed_t_pair("two", 3)
        + _completed_t_pair("three", 5)
    )
    cycles = recorded_t_cycles(rows, DAY, now=NOW)
    assert len(cycles) == 3
    assert all(cycle["state"] == "closed" for cycle in cycles)
    assert all(cycle["recorded_daily_limit_alert"] is True for cycle in cycles)
    assert all("最多2次" in cycle["warning"] for cycle in cycles)
    assert all(cycle["broker_reconciled"] is False for cycle in cycles)
    assert all(cycle["trade_execution_enabled"] is False for cycle in cycles)


def test_two_pairs_or_incomplete_third_cannot_be_called_compliant_or_over_limit():
    rows = _completed_t_pair("one", 1) + _completed_t_pair("two", 3)
    # An invalid third cycle is not a third confirmed closed pair.
    rows += [
        _record(
            ActionType.POSITIVE_T_SELL,
            _fill("invalid-third", OrderSide.BUY, "10", 5),
            key="three",
        ),
    ]
    cycles = recorded_t_cycles(rows, DAY, now=NOW)
    assert len(cycles) == 3
    assert {cycle["state"] for cycle in cycles} == {"closed", "conflict"}
    assert all(cycle["recorded_daily_limit_alert"] is None for cycle in cycles)
    assert all(cycle["broker_reconciled"] is False for cycle in cycles)


def test_daily_limit_lower_bound_is_per_symbol_not_per_plan_or_whole_account():
    rows = (
        _completed_t_pair("one", 1)
        + _completed_t_pair("two", 3)
        + _completed_t_pair("other", 5, symbol="000001")
    )
    cycles = recorded_t_cycles(rows, DAY, now=NOW)
    assert len(cycles) == 3
    assert all(cycle["recorded_daily_limit_alert"] is None for cycle in cycles)
    # A third same-symbol pair across a separate plan version still counts.
    third = _completed_t_pair("three", 5)
    for _, _, _, fill in third:
        fill.action = SimpleNamespace(plan_version_id="another-version")
    cycles = recorded_t_cycles(rows + third, DAY, now=NOW)
    assert len(cycles) == 4
    assert all(
        cycle["recorded_daily_limit_alert"] is True
        for cycle in cycles if cycle["symbol"] == "600000"
    )
    assert all(
        cycle["recorded_daily_limit_alert"] is None
        for cycle in cycles if cycle["symbol"] == "000001"
    )
