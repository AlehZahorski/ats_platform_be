"""cv parsing profiles

Revision ID: f1a2b3c4d5e6
Revises: e7f8a9b0c1d2
Create Date: 2026-04-06 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cv_parse_jobs",
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cv_url", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("raw_result", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("normalized_result", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("parser_version", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_cv_parse_jobs_application_id"), "cv_parse_jobs", ["application_id"], unique=False)
    op.create_index(op.f("ix_cv_parse_jobs_status"), "cv_parse_jobs", ["status"], unique=False)

    op.create_table(
        "candidate_profiles",
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("headline", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("skills", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("experience", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("education", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("parsing_status", sa.Text(), nullable=False),
        sa.Column("parsing_error", sa.Text(), nullable=True),
        sa.Column("last_parsed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("application_id"),
    )
    op.create_index(op.f("ix_candidate_profiles_application_id"), "candidate_profiles", ["application_id"], unique=True)
    op.create_index(op.f("ix_candidate_profiles_parsing_status"), "candidate_profiles", ["parsing_status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_candidate_profiles_parsing_status"), table_name="candidate_profiles")
    op.drop_index(op.f("ix_candidate_profiles_application_id"), table_name="candidate_profiles")
    op.drop_table("candidate_profiles")
    op.drop_index(op.f("ix_cv_parse_jobs_status"), table_name="cv_parse_jobs")
    op.drop_index(op.f("ix_cv_parse_jobs_application_id"), table_name="cv_parse_jobs")
    op.drop_table("cv_parse_jobs")
