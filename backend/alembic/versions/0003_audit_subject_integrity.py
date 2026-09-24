"""enforce exactly one persisted audit subject

Revision ID: 0003_audit_subject_integrity
Revises: 0002_m1_review_fixes
Create Date: 2026-09-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_audit_subject_integrity"
down_revision: str | None = "0002_m1_review_fixes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing M1 data is development-only. For rows that historically stored both subjects,
    # action_id is sufficient because TradeAction now uniquely determines its plan version.
    op.execute(
        "UPDATE audit_results SET plan_version_id = NULL "
        "WHERE plan_version_id IS NOT NULL AND action_id IS NOT NULL"
    )
    with op.batch_alter_table("audit_results") as batch:
        batch.drop_constraint("ck_audit_result_has_subject", type_="check")
        batch.create_check_constraint(
            "ck_audit_result_exactly_one_subject",
            "(plan_version_id IS NOT NULL AND action_id IS NULL) OR "
            "(plan_version_id IS NULL AND action_id IS NOT NULL)",
        )


def downgrade() -> None:
    with op.batch_alter_table("audit_results") as batch:
        batch.drop_constraint("ck_audit_result_exactly_one_subject", type_="check")
        batch.create_check_constraint(
            "ck_audit_result_has_subject",
            "plan_version_id IS NOT NULL OR action_id IS NOT NULL",
        )
