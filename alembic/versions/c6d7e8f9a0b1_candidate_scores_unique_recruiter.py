"""candidate_scores — restore one-score-per-(application, recruiter) invariant

Faza 2 (plan-naprawy) / audit_database: the historical UNIQUE (application_id,
recruiter_id) was lost from the live model, so nothing stopped duplicate scores
from the same recruiter on the same application. Re-add it as a PARTIAL unique
index limited to recruiter_id IS NOT NULL — a plain UNIQUE (or NULLS NOT
DISTINCT) would break ON DELETE SET NULL when two departed recruiters had scored
the same application (both rows become NULL and would collide).

Defensive: de-duplicate any existing rows (keep the highest id per group) before
creating the index so the migration is safe on dirty data.

Revision ID: c6d7e8f9a0b1
Revises: a4b5c6d7e8f9
Create Date: 2026-06-04 13:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c6d7e8f9a0b1"
down_revision: Union[str, None] = "a4b5c6d7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop duplicates (non-null recruiter) keeping the row with the largest id.
    op.execute(
        sa.text(
            """
            DELETE FROM candidate_scores a
            USING candidate_scores b
            WHERE a.recruiter_id IS NOT NULL
              AND a.recruiter_id = b.recruiter_id
              AND a.application_id = b.application_id
              AND a.id < b.id
            """
        )
    )
    op.create_index(
        "uq_candidate_scores_application_recruiter",
        "candidate_scores",
        ["application_id", "recruiter_id"],
        unique=True,
        postgresql_where=sa.text("recruiter_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_candidate_scores_application_recruiter", table_name="candidate_scores"
    )
