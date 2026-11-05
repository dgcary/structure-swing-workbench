"""Add an optional user-specified execution date to persisted trade actions.

Revision ID: 0004_m8_action_planned_for_date
Revises: 0003_audit_subject_integrity
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_m8_action_planned_for_date"
down_revision: str | None = "0003_audit_subject_integrity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("trade_actions") as batch:
        batch.add_column(sa.Column("planned_for_date", sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("trade_actions") as batch:
        batch.drop_column("planned_for_date")
