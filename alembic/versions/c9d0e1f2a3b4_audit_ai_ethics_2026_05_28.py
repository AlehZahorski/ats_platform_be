"""AI ethics audit follow-up — audit_ai_ethics_2026_05_28

Adds the schema bits needed by audit_ai_ethics findings:

- F-04  api_usage_logs.application_id (nullable UUID) + anthropic_request_id —
        every LLM call can now be traced back to the application it scored,
        and an external Anthropic request id is captured for incident response
        (EU AI Act art. 12 record-keeping, RODO art. 30).
- F-08  candidate_job_matches.match_status (text, default 'completed') —
        distinguishes pending / completed / llm_disabled / llm_failed so the
        recruiter UI can tell why a match is missing instead of treating
        "absent match" as "not a match".

Revision ID: c9d0e1f2a3b4
Revises: f8a9b0c1d2e3
Create Date: 2026-05-28 14:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, None] = "f8a9b0c1d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── F-04 — richer AI inference log ─────────────────────────────────────
    op.add_column(
        "api_usage_logs",
        sa.Column(
            "application_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("applications.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_api_usage_logs_application_id",
        "api_usage_logs",
        ["application_id"],
    )
    op.add_column(
        "api_usage_logs",
        sa.Column("anthropic_request_id", sa.String(length=64), nullable=True),
    )

    # ── F-08 — explicit match status ───────────────────────────────────────
    op.add_column(
        "candidate_job_matches",
        sa.Column(
            "match_status",
            sa.String(length=20),
            nullable=False,
            server_default="completed",
        ),
    )
    op.create_index(
        "ix_candidate_job_matches_match_status",
        "candidate_job_matches",
        ["match_status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_candidate_job_matches_match_status",
        table_name="candidate_job_matches",
    )
    op.drop_column("candidate_job_matches", "match_status")

    op.drop_column("api_usage_logs", "anthropic_request_id")
    op.drop_index("ix_api_usage_logs_application_id", table_name="api_usage_logs")
    op.drop_column("api_usage_logs", "application_id")
