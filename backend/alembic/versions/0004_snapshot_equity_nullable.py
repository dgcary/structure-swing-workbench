"""allow holdings-only snapshots without fabricated equity

Revision ID: 0004_snapshot_equity_nullable
Revises: 0003_audit_subject_integrity
Create Date: 2026-11-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004_snapshot_equity_nullable"
down_revision: str | None = "0003_audit_subject_integrity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 持仓 CSV 导入以快照锚定持仓；权益未知时保持 NULL，不以 0 冒充。
    with op.batch_alter_table("account_snapshots") as batch:
        batch.alter_column("total_equity", nullable=True)
        batch.alter_column("available_cash", nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM account_snapshots WHERE total_equity IS NULL OR available_cash IS NULL")
    with op.batch_alter_table("account_snapshots") as batch:
        batch.alter_column("available_cash", nullable=False)
        batch.alter_column("total_equity", nullable=False)
