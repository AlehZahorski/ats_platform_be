"""cv_parse_jobs: add language column

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-09 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cv_parse_jobs", sa.Column("language", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("cv_parse_jobs", "language")
