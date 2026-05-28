"""jobs classification — category, shift_system, employment_size, required_qualifications

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-05-23 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b4c5d6e7f8a9"
down_revision: Union[str, None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("category", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("shift_system", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("employment_size", sa.Text(), nullable=True))
    op.add_column(
        "jobs",
        sa.Column(
            "required_qualifications",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.create_index("ix_jobs_category", "jobs", ["category"])


def downgrade() -> None:
    op.drop_index("ix_jobs_category", table_name="jobs")
    op.drop_column("jobs", "required_qualifications")
    op.drop_column("jobs", "employment_size")
    op.drop_column("jobs", "shift_system")
    op.drop_column("jobs", "category")
