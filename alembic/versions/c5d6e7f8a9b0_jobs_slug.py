"""jobs.slug — public URL slug

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-05-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, None] = "b4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("slug", sa.Text(), nullable=True))
    # Unique per company so two companies can have /careers/foo without clashing.
    op.create_index(
        "uq_jobs_company_slug",
        "jobs",
        ["company_id", "slug"],
        unique=True,
        postgresql_where=sa.text("slug IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_jobs_company_slug", table_name="jobs")
    op.drop_column("jobs", "slug")
