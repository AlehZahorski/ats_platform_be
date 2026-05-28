"""drop jobs.description — consolidate into role_summary

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-05-16 09:00:00.000000

Backfill rule:
  • If role_summary is empty/null AND description has content → copy description into role_summary
  • Otherwise keep role_summary as-is (don't overwrite richer AI-generated content)
Then drop the column.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Backfill role_summary from description where it makes sense.
    op.execute("""
        UPDATE jobs
        SET role_summary = description
        WHERE (role_summary IS NULL OR btrim(role_summary) = '')
          AND description IS NOT NULL
          AND btrim(description) <> ''
    """)
    op.drop_column("jobs", "description")


def downgrade() -> None:
    op.add_column("jobs", sa.Column("description", sa.Text(), nullable=True))
    # Best-effort restore — copy role_summary back into description.
    op.execute("""
        UPDATE jobs
        SET description = role_summary
        WHERE role_summary IS NOT NULL
    """)
