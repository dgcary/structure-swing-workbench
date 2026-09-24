"""align M1 domain model with first review feedback

Revision ID: 0002_m1_review_fixes
Revises: 0001_domain_models
Create Date: 2026-09-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_m1_review_fixes"
down_revision: str | None = "0001_domain_models"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _state_enum(*values: str) -> sa.Enum:
    return sa.Enum(*values, name="plan_version_state", native_enum=False)


def _entry_mode_enum() -> sa.Enum:
    return sa.Enum(
        "single_price",
        "price_range",
        name="entry_mode",
        native_enum=False,
    )


def upgrade() -> None:
    with op.batch_alter_table("trade_plans") as batch:
        batch.add_column(sa.Column("user_note", sa.Text(), nullable=True))

    with op.batch_alter_table("trade_plan_versions") as batch:
        batch.add_column(sa.Column("entry_mode", _entry_mode_enum(), nullable=True))
        batch.add_column(
            sa.Column("planned_total_position_amount", sa.Numeric(20, 4), nullable=True)
        )
        batch.add_column(
            sa.Column("remaining_exit_condition_triggered", sa.Boolean(), nullable=True)
        )
        batch.alter_column(
            "state",
            existing_type=_state_enum(
                "pending_audit",
                "effective",
                "superseded",
                "rejected",
            ),
            type_=_state_enum(
                "draft",
                "pending_audit",
                "effective",
                "effective_with_override",
                "superseded",
                "rejected",
                "closed",
            ),
            existing_nullable=False,
        )
        batch.drop_column("user_note")

    op.drop_index("ix_trade_actions_plan_id", table_name="trade_actions")
    with op.batch_alter_table("trade_actions") as batch:
        batch.drop_column("plan_id")


def downgrade() -> None:
    with op.batch_alter_table("trade_actions") as batch:
        batch.add_column(sa.Column("plan_id", sa.String(length=36), nullable=True))

    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            UPDATE trade_actions
            SET plan_id = (
                SELECT trade_plan_versions.plan_id
                FROM trade_plan_versions
                WHERE trade_plan_versions.id = trade_actions.plan_version_id
            )
            """
        )
    )

    with op.batch_alter_table("trade_actions") as batch:
        batch.alter_column("plan_id", existing_type=sa.String(length=36), nullable=False)
        batch.create_foreign_key(
            "fk_trade_actions_plan_id_trade_plans",
            "trade_plans",
            ["plan_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    op.create_index("ix_trade_actions_plan_id", "trade_actions", ["plan_id"])

    with op.batch_alter_table("trade_plan_versions") as batch:
        batch.add_column(sa.Column("user_note", sa.Text(), nullable=True))
        batch.alter_column(
            "state",
            existing_type=_state_enum(
                "draft",
                "pending_audit",
                "effective",
                "effective_with_override",
                "superseded",
                "rejected",
                "closed",
            ),
            type_=_state_enum(
                "pending_audit",
                "effective",
                "superseded",
                "rejected",
            ),
            existing_nullable=False,
        )
        batch.drop_column("remaining_exit_condition_triggered")
        batch.drop_column("planned_total_position_amount")
        batch.drop_column("entry_mode")

    with op.batch_alter_table("trade_plans") as batch:
        batch.drop_column("user_note")
