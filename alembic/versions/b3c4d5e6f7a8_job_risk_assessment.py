"""job risk assessment — new tables, migrate analysis, add role fields

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-05-15 12:00:00.000000

Changes:
- Create job_analyses       (migrated from jobs.analysis_*)
- Create job_risk_assessments
- Create risk_items
- Create mitigation_actions
- Add jobs.role_scope, jobs.role_deliverables
- Drop jobs.analysis_* columns
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. job_analyses ──────────────────────────────────────────────────────
    op.create_table(
        "job_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("market_position", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("strengths", sa.JSON(), nullable=True),
        sa.Column("improvements", sa.JSON(), nullable=True),
        sa.Column("candidate_impact", sa.Text(), nullable=True),
        sa.Column("urgency_message", sa.Text(), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_job_analyses_job_id", "job_analyses", ["job_id"])

    # Migrate existing analysis data from jobs → job_analyses
    op.execute("""
        INSERT INTO job_analyses (
            id, created_at, updated_at, job_id,
            score, market_position, summary, strengths, improvements,
            candidate_impact, urgency_message, analyzed_at
        )
        SELECT
            gen_random_uuid(), now(), now(), id,
            analysis_score, analysis_market_position, analysis_summary,
            analysis_strengths, analysis_improvements,
            analysis_candidate_impact, analysis_urgency_message, analysis_at
        FROM jobs
        WHERE analysis_score IS NOT NULL
           OR analysis_market_position IS NOT NULL
           OR analysis_summary IS NOT NULL
    """)

    # ── 2. job_risk_assessments ───────────────────────────────────────────────
    op.create_table(
        "job_risk_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("level", sa.Text(), nullable=True),
        sa.Column("factors", sa.JSON(), nullable=True),
        sa.Column("recommendations", sa.JSON(), nullable=True),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_job_risk_assessments_job_id", "job_risk_assessments", ["job_id"])

    # ── 3. risk_items ─────────────────────────────────────────────────────────
    op.create_table(
        "risk_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False, server_default="medium"),
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_risk_items_job_id", "risk_items", ["job_id"])

    # ── 4. mitigation_actions ─────────────────────────────────────────────────
    op.create_table(
        "mitigation_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_mitigation_actions_job_id", "mitigation_actions", ["job_id"])

    # ── 5. New fields on jobs ─────────────────────────────────────────────────
    op.add_column("jobs", sa.Column("role_scope", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("role_deliverables", sa.Text(), nullable=True))

    # ── 6. Drop analysis columns from jobs ────────────────────────────────────
    op.drop_column("jobs", "analysis_score")
    op.drop_column("jobs", "analysis_market_position")
    op.drop_column("jobs", "analysis_summary")
    op.drop_column("jobs", "analysis_strengths")
    op.drop_column("jobs", "analysis_improvements")
    op.drop_column("jobs", "analysis_candidate_impact")
    op.drop_column("jobs", "analysis_urgency_message")
    op.drop_column("jobs", "analysis_at")


def downgrade() -> None:
    # Restore analysis columns to jobs
    op.add_column("jobs", sa.Column("analysis_score", sa.Integer(), nullable=True))
    op.add_column("jobs", sa.Column("analysis_market_position", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("analysis_summary", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("analysis_strengths", sa.JSON(), nullable=True))
    op.add_column("jobs", sa.Column("analysis_improvements", sa.JSON(), nullable=True))
    op.add_column("jobs", sa.Column("analysis_candidate_impact", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("analysis_urgency_message", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("analysis_at", sa.DateTime(timezone=True), nullable=True))

    # Restore data from job_analyses back to jobs
    op.execute("""
        UPDATE jobs j
        SET
            analysis_score            = ja.score,
            analysis_market_position  = ja.market_position,
            analysis_summary          = ja.summary,
            analysis_strengths        = ja.strengths,
            analysis_improvements     = ja.improvements,
            analysis_candidate_impact = ja.candidate_impact,
            analysis_urgency_message  = ja.urgency_message,
            analysis_at               = ja.analyzed_at
        FROM job_analyses ja
        WHERE ja.job_id = j.id
    """)

    op.drop_column("jobs", "role_scope")
    op.drop_column("jobs", "role_deliverables")

    op.drop_index("ix_mitigation_actions_job_id", "mitigation_actions")
    op.drop_table("mitigation_actions")

    op.drop_index("ix_risk_items_job_id", "risk_items")
    op.drop_table("risk_items")

    op.drop_index("ix_job_risk_assessments_job_id", "job_risk_assessments")
    op.drop_table("job_risk_assessments")

    op.drop_index("ix_job_analyses_job_id", "job_analyses")
    op.drop_table("job_analyses")
