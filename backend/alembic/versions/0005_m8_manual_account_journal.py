"""Separate append-only self-reported account journal.

Revision ID: 0005_m8_manual_account_journal
Revises: 0004_m8_action_planned_for_date
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_m8_manual_account_journal"
down_revision: str | None = "0004_m8_action_planned_for_date"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "manual_journal_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False, unique=True),
        sa.Column("recorded_at", sa.String(40), nullable=False),
        sa.Column("observed_at", sa.String(40), nullable=False),
        sa.Column("available_cash", sa.Numeric(20, 4), nullable=True),
        sa.Column("total_equity", sa.Numeric(20, 4), nullable=True),
        sa.Column("lots", sa.JSON(), nullable=False),
        sa.Column("operation", sa.JSON(), nullable=True),
        sa.Column("note", sa.String(200), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("manual_journal_revisions")
