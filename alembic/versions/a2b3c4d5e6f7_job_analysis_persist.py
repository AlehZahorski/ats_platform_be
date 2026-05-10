"""job analysis persist

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-05-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("analysis_score", sa.Integer(), nullable=True))
    op.add_column("jobs", sa.Column("analysis_market_position", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("analysis_summary", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("analysis_strengths", sa.JSON(), nullable=True))
    op.add_column("jobs", sa.Column("analysis_improvements", sa.JSON(), nullable=True))
    op.add_column("jobs", sa.Column("analysis_candidate_impact", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("analysis_urgency_message", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("analysis_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "analysis_at")
    op.drop_column("jobs", "analysis_urgency_message")
    op.drop_column("jobs", "analysis_candidate_impact")
    op.drop_column("jobs", "analysis_improvements")
    op.drop_column("jobs", "analysis_strengths")
    op.drop_column("jobs", "analysis_summary")
    op.drop_column("jobs", "analysis_market_position")
    op.drop_column("jobs", "analysis_score")
