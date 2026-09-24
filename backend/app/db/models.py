from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin
from app.domain.enums import (
    ActionStatus,
    ActionType,
    AuditLevel,
    LabeledEnum,
    OrderSide,
    PlanStatus,
    PlanVersionState,
    PositionBucketType,
    SetupType,
    StructureStage,
    TargetType,
)

PRICE = Numeric(18, 4)
QUANTITY = Numeric(20, 4)
MONEY = Numeric(20, 4)
PERCENT = Numeric(8, 4)


def enum_type(enum_class: type[LabeledEnum], name: str) -> SAEnum:
    return SAEnum(
        enum_class,
        name=name,
        native_enum=False,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )


class TradePlan(IdMixin, TimestampMixin, Base):
    __tablename__ = "trade_plans"
    __table_args__ = (
        Index(
            "uq_trade_plans_one_active_per_instrument",
            "instrument_code",
            unique=True,
            postgresql_where=text("is_active IS TRUE"),
            sqlite_where=text("is_active = 1"),
        ),
    )

    instrument_code: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    instrument_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[PlanStatus] = mapped_column(
        enum_type(PlanStatus, "plan_status"), nullable=False, default=PlanStatus.ACTIVE
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    versions: Mapped[list[TradePlanVersion]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="TradePlanVersion.version_number",
    )
    actions: Mapped[list[TradeAction]] = relationship(back_populates="plan")


class TradePlanVersion(IdMixin, TimestampMixin, Base):
    __tablename__ = "trade_plan_versions"
    __table_args__ = (
        UniqueConstraint("plan_id", "version_number", name="uq_trade_plan_version_number"),
        Index(
            "uq_trade_plan_versions_one_effective",
            "plan_id",
            unique=True,
            postgresql_where=text("is_effective IS TRUE"),
            sqlite_where=text("is_effective = 1"),
        ),
    )

    plan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trade_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    based_on_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("trade_plan_versions.id"), nullable=True
    )
    state: Mapped[PlanVersionState] = mapped_column(
        enum_type(PlanVersionState, "plan_version_state"),
        nullable=False,
        default=PlanVersionState.PENDING_AUDIT,
    )
    is_effective: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Subjective structure facts are stored only as explicit user input.
    # No inference is performed here.
    setup_type: Mapped[SetupType | None] = mapped_column(
        enum_type(SetupType, "setup_type"), nullable=True
    )
    structure_stage: Mapped[StructureStage | None] = mapped_column(
        enum_type(StructureStage, "structure_stage"), nullable=True
    )
    structure_low_price: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    key_support_price: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    key_resistance_price: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    reversal_confirmed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    structure_invalidated: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    structure_invalidation_price: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    structure_invalidation_condition: Mapped[str | None] = mapped_column(Text, nullable=True)

    planned_total_position_pct: Mapped[Decimal | None] = mapped_column(PERCENT, nullable=True)
    initial_entry_price_low: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    initial_entry_price_high: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    initial_entry_pct: Mapped[Decimal | None] = mapped_column(PERCENT, nullable=True)
    confirmation_add_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confirmation_trigger_price: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    confirmation_add_pct: Mapped[Decimal | None] = mapped_column(PERCENT, nullable=True)
    t_reserve_pct: Mapped[Decimal | None] = mapped_column(PERCENT, nullable=True)

    first_target_price: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    first_target_type: Mapped[TargetType | None] = mapped_column(
        enum_type(TargetType, "target_type"), nullable=True
    )
    first_target_reduce_pct: Mapped[Decimal | None] = mapped_column(PERCENT, nullable=True)
    remaining_exit_condition: Mapped[str | None] = mapped_column(Text, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    user_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    plan: Mapped[TradePlan] = relationship(back_populates="versions")
    based_on_version: Mapped[TradePlanVersion | None] = relationship(
        remote_side="TradePlanVersion.id", foreign_keys=[based_on_version_id]
    )
    actions: Mapped[list[TradeAction]] = relationship(back_populates="plan_version")
    audit_results: Mapped[list[AuditResult]] = relationship(back_populates="plan_version")


class TradeAction(IdMixin, TimestampMixin, Base):
    __tablename__ = "trade_actions"

    plan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trade_plans.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    plan_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("trade_plan_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    action_type: Mapped[ActionType] = mapped_column(
        enum_type(ActionType, "action_type"), nullable=False
    )
    side: Mapped[OrderSide] = mapped_column(enum_type(OrderSide, "order_side"), nullable=False)
    status: Mapped[ActionStatus] = mapped_column(
        enum_type(ActionStatus, "action_status"), nullable=False, default=ActionStatus.PLANNED
    )
    planned_price_low: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    planned_price_high: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    planned_quantity: Mapped[Decimal | None] = mapped_column(QUANTITY, nullable=True)
    planned_position_pct: Mapped[Decimal | None] = mapped_column(PERCENT, nullable=True)
    t_cycle_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    plan: Mapped[TradePlan] = relationship(back_populates="actions")
    plan_version: Mapped[TradePlanVersion] = relationship(back_populates="actions")
    fills: Mapped[list[ExecutionFill]] = relationship(
        back_populates="action", cascade="all, delete-orphan", order_by="ExecutionFill.executed_at"
    )
    audit_results: Mapped[list[AuditResult]] = relationship(back_populates="action")


class ExecutionFill(IdMixin, TimestampMixin, Base):
    __tablename__ = "execution_fills"

    action_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trade_actions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    side: Mapped[OrderSide] = mapped_column(enum_type(OrderSide, "fill_side"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    price: Mapped[Decimal] = mapped_column(PRICE, nullable=False)
    fee: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal(0))
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    external_execution_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    action: Mapped[TradeAction] = relationship(back_populates="fills")


class AccountSnapshot(IdMixin, TimestampMixin, Base):
    __tablename__ = "account_snapshots"

    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    total_equity: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    available_cash: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    source_note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    positions: Mapped[list[PositionSnapshot]] = relationship(
        back_populates="account_snapshot", cascade="all, delete-orphan"
    )


class PositionSnapshot(IdMixin, TimestampMixin, Base):
    __tablename__ = "position_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "account_snapshot_id", "instrument_code", name="uq_position_snapshot_instrument"
        ),
    )

    account_snapshot_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("account_snapshots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    instrument_code: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    instrument_name: Mapped[str] = mapped_column(String(64), nullable=False)
    total_quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    market_value: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    broker_cost_price: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)

    account_snapshot: Mapped[AccountSnapshot] = relationship(back_populates="positions")
    buckets: Mapped[list[PositionBucketSnapshot]] = relationship(
        back_populates="position_snapshot", cascade="all, delete-orphan"
    )


class PositionBucketSnapshot(IdMixin, TimestampMixin, Base):
    __tablename__ = "position_bucket_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "position_snapshot_id", "bucket_type", name="uq_position_snapshot_bucket_type"
        ),
    )

    position_snapshot_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("position_snapshots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    bucket_type: Mapped[PositionBucketType] = mapped_column(
        enum_type(PositionBucketType, "position_bucket_type"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    strategy_cost_price: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    effective_cost_price: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    realized_t_pnl: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)

    position_snapshot: Mapped[PositionSnapshot] = relationship(back_populates="buckets")


class AuditResult(IdMixin, TimestampMixin, Base):
    __tablename__ = "audit_results"
    __table_args__ = (
        CheckConstraint(
            "plan_version_id IS NOT NULL OR action_id IS NOT NULL",
            name="ck_audit_result_has_subject",
        ),
    )

    plan_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("trade_plan_versions.id", ondelete="RESTRICT"), nullable=True
    )
    action_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("trade_actions.id", ondelete="RESTRICT"), nullable=True
    )
    level: Mapped[AuditLevel] = mapped_column(
        enum_type(AuditLevel, "audit_level"), nullable=False
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False, default="m1-model-only")
    details: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSON, nullable=True)

    plan_version: Mapped[TradePlanVersion | None] = relationship(back_populates="audit_results")
    action: Mapped[TradeAction | None] = relationship(back_populates="audit_results")
    overrides: Mapped[list[ManualOverride]] = relationship(
        back_populates="audit_result", cascade="all, delete-orphan"
    )


class ManualOverride(IdMixin, TimestampMixin, Base):
    __tablename__ = "manual_overrides"

    audit_result_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("audit_results.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    operator: Mapped[str] = mapped_column(String(64), nullable=False, default="用户")
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    audit_result: Mapped[AuditResult] = relationship(back_populates="overrides")
