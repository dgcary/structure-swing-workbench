"""create M1 trading domain models

Revision ID: 0001_domain_models
Revises:
Create Date: 2026-09-24
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0001_domain_models"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False)


def upgrade() -> None:
    op.create_table(
        "trade_plans",
        sa.Column("instrument_code", sa.String(length=16), nullable=False),
        sa.Column("instrument_name", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            _enum("plan_status", "active", "exiting", "closed", "cancelled"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trade_plans_instrument_code", "trade_plans", ["instrument_code"])
    op.create_index(
        "uq_trade_plans_one_active_per_instrument",
        "trade_plans",
        ["instrument_code"],
        unique=True,
        postgresql_where=sa.text("is_active IS TRUE"),
        sqlite_where=sa.text("is_active = 1"),
    )

    op.create_table(
        "trade_plan_versions",
        sa.Column("plan_id", sa.String(length=36), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("based_on_version_id", sa.String(length=36), nullable=True),
        sa.Column(
            "state",
            _enum(
                "plan_version_state",
                "pending_audit",
                "effective",
                "superseded",
                "rejected",
            ),
            nullable=False,
        ),
        sa.Column("is_effective", sa.Boolean(), nullable=False),
        sa.Column("version_reason", sa.String(length=255), nullable=True),
        sa.Column("setup_type", _enum("setup_type", "c", "a", "b"), nullable=True),
        sa.Column(
            "structure_stage",
            _enum("structure_stage", "early", "middle", "late"),
            nullable=True,
        ),
        sa.Column("structure_low_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("key_support_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("key_resistance_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("reversal_confirmed", sa.Boolean(), nullable=True),
        sa.Column("structure_invalidated", sa.Boolean(), nullable=True),
        sa.Column("structure_invalidation_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("structure_invalidation_condition", sa.Text(), nullable=True),
        sa.Column("planned_total_position_pct", sa.Numeric(8, 4), nullable=True),
        sa.Column("initial_entry_price_low", sa.Numeric(18, 4), nullable=True),
        sa.Column("initial_entry_price_high", sa.Numeric(18, 4), nullable=True),
        sa.Column("initial_entry_pct", sa.Numeric(8, 4), nullable=True),
        sa.Column("confirmation_add_enabled", sa.Boolean(), nullable=False),
        sa.Column("confirmation_trigger_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("confirmation_add_pct", sa.Numeric(8, 4), nullable=True),
        sa.Column("t_reserve_pct", sa.Numeric(8, 4), nullable=True),
        sa.Column("first_target_price", sa.Numeric(18, 4), nullable=True),
        sa.Column(
            "first_target_type",
            _enum("target_type", "prior_high", "range_top", "major_resistance", "other"),
            nullable=True,
        ),
        sa.Column("first_target_reduce_pct", sa.Numeric(8, 4), nullable=True),
        sa.Column("remaining_exit_condition", sa.Text(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("user_note", sa.Text(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["based_on_version_id"], ["trade_plan_versions.id"]),
        sa.ForeignKeyConstraint(["plan_id"], ["trade_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "version_number", name="uq_trade_plan_version_number"),
    )
    op.create_index("ix_trade_plan_versions_plan_id", "trade_plan_versions", ["plan_id"])
    op.create_index(
        "uq_trade_plan_versions_one_effective",
        "trade_plan_versions",
        ["plan_id"],
        unique=True,
        postgresql_where=sa.text("is_effective IS TRUE"),
        sqlite_where=sa.text("is_effective = 1"),
    )

    op.create_table(
        "trade_actions",
        sa.Column("plan_id", sa.String(length=36), nullable=False),
        sa.Column("plan_version_id", sa.String(length=36), nullable=False),
        sa.Column(
            "action_type",
            _enum(
                "action_type",
                "initial_entry",
                "confirmation_add",
                "ordinary_add",
                "positive_t_sell",
                "positive_t_buyback",
                "reverse_t_buy",
                "reverse_t_sell",
                "take_profit",
                "reduce",
                "exit",
            ),
            nullable=False,
        ),
        sa.Column("side", _enum("order_side", "buy", "sell"), nullable=False),
        sa.Column(
            "status",
            _enum(
                "action_status",
                "planned",
                "audited",
                "executing",
                "partially_filled",
                "filled",
                "cancelled",
                "rejected",
            ),
            nullable=False,
        ),
        sa.Column("planned_price_low", sa.Numeric(18, 4), nullable=True),
        sa.Column("planned_price_high", sa.Numeric(18, 4), nullable=True),
        sa.Column("planned_quantity", sa.Numeric(20, 4), nullable=True),
        sa.Column("planned_position_pct", sa.Numeric(8, 4), nullable=True),
        sa.Column("t_cycle_key", sa.String(length=64), nullable=True),
        sa.Column("user_note", sa.Text(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["trade_plans.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["plan_version_id"], ["trade_plan_versions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trade_actions_plan_id", "trade_actions", ["plan_id"])
    op.create_index("ix_trade_actions_plan_version_id", "trade_actions", ["plan_version_id"])

    op.create_table(
        "execution_fills",
        sa.Column("action_id", sa.String(length=36), nullable=False),
        sa.Column("side", _enum("fill_side", "buy", "sell"), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 4), nullable=False),
        sa.Column("price", sa.Numeric(18, 4), nullable=False),
        sa.Column("fee", sa.Numeric(20, 4), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("external_execution_id", sa.String(length=128), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["action_id"], ["trade_actions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_execution_fills_action_id", "execution_fills", ["action_id"])

    op.create_table(
        "account_snapshots",
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_equity", sa.Numeric(20, 4), nullable=False),
        sa.Column("available_cash", sa.Numeric(20, 4), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_note", sa.String(length=255), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_account_snapshots_captured_at", "account_snapshots", ["captured_at"])

    op.create_table(
        "position_snapshots",
        sa.Column("account_snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("instrument_code", sa.String(length=16), nullable=False),
        sa.Column("instrument_name", sa.String(length=64), nullable=False),
        sa.Column("total_quantity", sa.Numeric(20, 4), nullable=False),
        sa.Column("market_value", sa.Numeric(20, 4), nullable=True),
        sa.Column("broker_cost_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_snapshot_id"], ["account_snapshots.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "account_snapshot_id", "instrument_code", name="uq_position_snapshot_instrument"
        ),
    )
    op.create_index(
        "ix_position_snapshots_account_snapshot_id", "position_snapshots", ["account_snapshot_id"]
    )
    op.create_index(
        "ix_position_snapshots_instrument_code", "position_snapshots", ["instrument_code"]
    )

    op.create_table(
        "position_bucket_snapshots",
        sa.Column("position_snapshot_id", sa.String(length=36), nullable=False),
        sa.Column(
            "bucket_type",
            _enum("position_bucket_type", "core", "t"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Numeric(20, 4), nullable=False),
        sa.Column("strategy_cost_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("effective_cost_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("realized_t_pnl", sa.Numeric(20, 4), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["position_snapshot_id"], ["position_snapshots.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "position_snapshot_id", "bucket_type", name="uq_position_snapshot_bucket_type"
        ),
    )
    op.create_index(
        "ix_position_bucket_snapshots_position_snapshot_id",
        "position_bucket_snapshots",
        ["position_snapshot_id"],
    )

    op.create_table(
        "audit_results",
        sa.Column("plan_version_id", sa.String(length=36), nullable=True),
        sa.Column("action_id", sa.String(length=36), nullable=True),
        sa.Column(
            "level",
            _enum("audit_level", "pass", "warning", "overridable_fail", "hard_fail"),
            nullable=False,
        ),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("engine_version", sa.String(length=64), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "plan_version_id IS NOT NULL OR action_id IS NOT NULL",
            name="ck_audit_result_has_subject",
        ),
        sa.ForeignKeyConstraint(["action_id"], ["trade_actions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["plan_version_id"], ["trade_plan_versions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "manual_overrides",
        sa.Column("audit_result_id", sa.String(length=36), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("operator", sa.String(length=64), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["audit_result_id"], ["audit_results.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_manual_overrides_audit_result_id", "manual_overrides", ["audit_result_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_manual_overrides_audit_result_id", table_name="manual_overrides")
    op.drop_table("manual_overrides")
    op.drop_table("audit_results")
    op.drop_index(
        "ix_position_bucket_snapshots_position_snapshot_id",
        table_name="position_bucket_snapshots",
    )
    op.drop_table("position_bucket_snapshots")
    op.drop_index("ix_position_snapshots_instrument_code", table_name="position_snapshots")
    op.drop_index("ix_position_snapshots_account_snapshot_id", table_name="position_snapshots")
    op.drop_table("position_snapshots")
    op.drop_index("ix_account_snapshots_captured_at", table_name="account_snapshots")
    op.drop_table("account_snapshots")
    op.drop_index("ix_execution_fills_action_id", table_name="execution_fills")
    op.drop_table("execution_fills")
    op.drop_index("ix_trade_actions_plan_version_id", table_name="trade_actions")
    op.drop_index("ix_trade_actions_plan_id", table_name="trade_actions")
    op.drop_table("trade_actions")
    op.drop_index("uq_trade_plan_versions_one_effective", table_name="trade_plan_versions")
    op.drop_index("ix_trade_plan_versions_plan_id", table_name="trade_plan_versions")
    op.drop_table("trade_plan_versions")
    op.drop_index("uq_trade_plans_one_active_per_instrument", table_name="trade_plans")
    op.drop_index("ix_trade_plans_instrument_code", table_name="trade_plans")
    op.drop_table("trade_plans")
