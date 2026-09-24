from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import DateTime
from sqlalchemy.orm import Session

from app.db.models import (
    AccountSnapshot,
    ExecutionFill,
    PositionBucketSnapshot,
    PositionSnapshot,
)
from app.domain.enums import AuditLevel, PlanStatus, PositionBucketType


def test_account_position_and_core_t_buckets_are_separate(session: Session) -> None:
    snapshot = AccountSnapshot(
        captured_at=datetime(2026, 9, 24, 15, 0, tzinfo=UTC),
        total_equity=Decimal(200000),
        available_cash=Decimal(100000),
        source="manual",
    )
    position = PositionSnapshot(
        instrument_code="600000",
        instrument_name="浦发银行",
        total_quantity=Decimal(10000),
        market_value=Decimal(120000),
        broker_cost_price=Decimal("11.50"),
    )
    position.buckets.extend(
        [
            PositionBucketSnapshot(
                bucket_type=PositionBucketType.CORE,
                quantity=Decimal(7000),
                strategy_cost_price=Decimal("11.20"),
            ),
            PositionBucketSnapshot(
                bucket_type=PositionBucketType.T,
                quantity=Decimal(3000),
                strategy_cost_price=Decimal("11.90"),
                realized_t_pnl=Decimal(350),
            ),
        ]
    )
    snapshot.positions.append(position)
    session.add(snapshot)
    session.flush()

    assert {bucket.bucket_type for bucket in position.buckets} == {
        PositionBucketType.CORE,
        PositionBucketType.T,
    }


def test_user_visible_enums_have_chinese_labels() -> None:
    assert AuditLevel.PASS.label_zh == "通过"
    assert AuditLevel.HARD_FAIL.label_zh == "硬性失败"
    assert PlanStatus.ACTIVE.label_zh == "有效"
    assert PositionBucketType.CORE.label_zh == "核心仓"


def test_all_explicit_datetime_columns_keep_timezone_semantics() -> None:
    models_and_columns = (
        (AccountSnapshot, "captured_at"),
        (AccountSnapshot, "created_at"),
        (ExecutionFill, "executed_at"),
        (ExecutionFill, "created_at"),
    )
    for model, column_name in models_and_columns:
        column_type = model.__table__.c[column_name].type
        assert isinstance(column_type, DateTime)
        assert column_type.timezone is True
