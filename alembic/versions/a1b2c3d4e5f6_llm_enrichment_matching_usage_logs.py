"""llm enrichment matching usage logs

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-05-09 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # candidate_profiles — new LLM enrichment columns
    # -------------------------------------------------------------------------
    op.add_column("candidate_profiles", sa.Column("parser_version", sa.Text(), nullable=False, server_default="v1-regex"))
    op.add_column("candidate_profiles", sa.Column("personal_summary", sa.Text(), nullable=True))
    op.add_column("candidate_profiles", sa.Column("executive_summary", sa.Text(), nullable=True))
    op.add_column("candidate_profiles", sa.Column("location", sa.Text(), nullable=True))
    op.add_column("candidate_profiles", sa.Column("linkedin_url", sa.Text(), nullable=True))
    op.add_column("candidate_profiles", sa.Column("github_url", sa.Text(), nullable=True))
    op.add_column("candidate_profiles", sa.Column("technical_skills", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("candidate_profiles", sa.Column("soft_skills", postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column("candidate_profiles", sa.Column("languages", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("candidate_profiles", sa.Column("certifications", postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column("candidate_profiles", sa.Column("hobbies", postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column("candidate_profiles", sa.Column("volunteering", postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column("candidate_profiles", sa.Column("total_experience_years", sa.Float(), nullable=True))
    op.add_column("candidate_profiles", sa.Column("seniority_estimate", sa.Text(), nullable=True))
    op.add_column("candidate_profiles", sa.Column("strengths", postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column("candidate_profiles", sa.Column("red_flags", postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column("candidate_profiles", sa.Column("personality_signals", postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column("candidate_profiles", sa.Column("culture_fit_notes", sa.Text(), nullable=True))

    op.create_index("ix_candidate_profiles_parser_version", "candidate_profiles", ["parser_version"])
    op.create_index("ix_candidate_profiles_seniority_estimate", "candidate_profiles", ["seniority_estimate"])
    op.create_index(
        "ix_candidate_profiles_technical_skills", "candidate_profiles", ["technical_skills"],
        postgresql_using="gin",
        postgresql_ops={"technical_skills": "jsonb_path_ops"},
    )
    op.create_index(
        "ix_candidate_profiles_languages", "candidate_profiles", ["languages"],
        postgresql_using="gin",
        postgresql_ops={"languages": "jsonb_path_ops"},
    )

    # -------------------------------------------------------------------------
    # cv_parse_jobs — LLM metadata columns
    # -------------------------------------------------------------------------
    op.add_column("cv_parse_jobs", sa.Column("llm_model", sa.Text(), nullable=True))
    op.add_column("cv_parse_jobs", sa.Column("token_usage", postgresql.JSON(astext_type=sa.Text()), nullable=True))

    # -------------------------------------------------------------------------
    # candidate_job_matches — new table
    # -------------------------------------------------------------------------
    op.create_table(
        "candidate_job_matches",
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("match_score", sa.Integer(), nullable=True),
        sa.Column("fit_score", sa.Integer(), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("strengths_match", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("gaps", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("llm_model", sa.Text(), nullable=True),
        sa.Column("token_usage", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_profile_id"], ["candidate_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_candidate_job_matches_application_id", "candidate_job_matches", ["application_id"])
    op.create_index("ix_candidate_job_matches_candidate_profile_id", "candidate_job_matches", ["candidate_profile_id"])
    op.create_index("ix_candidate_job_matches_job_id", "candidate_job_matches", ["job_id"])
    op.create_index("ix_candidate_job_matches_match_score", "candidate_job_matches", ["match_score"])
    op.create_index("ix_candidate_job_matches_fit_score", "candidate_job_matches", ["fit_score"])

    # -------------------------------------------------------------------------
    # api_usage_logs — new table (partitioned by created_at monthly)
    # -------------------------------------------------------------------------
    op.create_table(
        "api_usage_logs",
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("llm_model", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_api_usage_logs_company_created",
        "api_usage_logs",
        ["company_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_api_usage_logs_company_created", table_name="api_usage_logs")
    op.drop_table("api_usage_logs")

    op.drop_index("ix_candidate_job_matches_fit_score", table_name="candidate_job_matches")
    op.drop_index("ix_candidate_job_matches_match_score", table_name="candidate_job_matches")
    op.drop_index("ix_candidate_job_matches_job_id", table_name="candidate_job_matches")
    op.drop_index("ix_candidate_job_matches_candidate_profile_id", table_name="candidate_job_matches")
    op.drop_index("ix_candidate_job_matches_application_id", table_name="candidate_job_matches")
    op.drop_table("candidate_job_matches")

    op.drop_column("cv_parse_jobs", "token_usage")
    op.drop_column("cv_parse_jobs", "llm_model")

    op.drop_index("ix_candidate_profiles_languages", table_name="candidate_profiles")
    op.drop_index("ix_candidate_profiles_technical_skills", table_name="candidate_profiles")
    op.drop_index("ix_candidate_profiles_seniority_estimate", table_name="candidate_profiles")
    op.drop_index("ix_candidate_profiles_parser_version", table_name="candidate_profiles")
    op.drop_column("candidate_profiles", "culture_fit_notes")
    op.drop_column("candidate_profiles", "personality_signals")
    op.drop_column("candidate_profiles", "red_flags")
    op.drop_column("candidate_profiles", "strengths")
    op.drop_column("candidate_profiles", "seniority_estimate")
    op.drop_column("candidate_profiles", "total_experience_years")
    op.drop_column("candidate_profiles", "volunteering")
    op.drop_column("candidate_profiles", "hobbies")
    op.drop_column("candidate_profiles", "certifications")
    op.drop_column("candidate_profiles", "languages")
    op.drop_column("candidate_profiles", "soft_skills")
    op.drop_column("candidate_profiles", "technical_skills")
    op.drop_column("candidate_profiles", "github_url")
    op.drop_column("candidate_profiles", "linkedin_url")
    op.drop_column("candidate_profiles", "location")
    op.drop_column("candidate_profiles", "executive_summary")
    op.drop_column("candidate_profiles", "personal_summary")
    op.drop_column("candidate_profiles", "parser_version")
