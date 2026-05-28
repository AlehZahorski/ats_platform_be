"""match recommendation rename — hire→top_candidate, reject→not_a_match

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-05-15 18:00:00.000000

`candidate_job_matches.recommendation` is a free Text column (not enum), so
this is a pure data migration. Mapping:
  hire   → top_candidate
  reject → not_a_match
  consider → consider (unchanged)
"""
from typing import Sequence, Union

from alembic import op

revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        UPDATE candidate_job_matches
        SET recommendation = 'top_candidate'
        WHERE recommendation = 'hire'
    """)
    op.execute("""
        UPDATE candidate_job_matches
        SET recommendation = 'not_a_match'
        WHERE recommendation = 'reject'
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE candidate_job_matches
        SET recommendation = 'hire'
        WHERE recommendation = 'top_candidate'
    """)
    op.execute("""
        UPDATE candidate_job_matches
        SET recommendation = 'reject'
        WHERE recommendation = 'not_a_match'
    """)
