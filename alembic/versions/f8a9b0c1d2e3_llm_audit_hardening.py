"""LLM hardening — audit_ai_2026_05_28 follow-up

Adds the schema bits needed by audit findings:

- F-02  applications.ai_profiling_consented_at (NULL = consent not granted →
        backend will redact PII before sending the CV to Anthropic).
- F-09  candidate_job_matches.match_key (sha256 of profile+job snapshot) with
        a UNIQUE constraint — second match call for the same inputs is a no-op.
- F-16  candidate_profiles.evidence_quotes (JSONB) — replaces the binary
        ``personality_signals`` whose categorical labels invited bias.
        We keep ``personality_signals`` for one release as a read-only column
        so the existing rows stay visible; the column is dropped in a later
        migration after the UI migrates.
- F-20  api_usage_logs.prompt_name + prompt_version — every LLM call now
        records which prompt template (and which hash) produced it.
- F-22  api_usage_logs.correlation_id — request-scoped UUID for tracing.

Revision ID: f8a9b0c1d2e3
Revises: f7a8b9c0d1e2
Create Date: 2026-05-28 12:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f8a9b0c1d2e3"
down_revision: Union[str, None] = "f7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── F-02 — RODO opt-in tracking ────────────────────────────────────────
    op.add_column(
        "applications",
        sa.Column(
            "ai_profiling_consented_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the candidate granted consent for AI profiling. NULL = no consent.",
        ),
    )

    # ── F-09 — match idempotency ───────────────────────────────────────────
    op.add_column(
        "candidate_job_matches",
        sa.Column("match_key", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_candidate_job_matches_match_key",
        "candidate_job_matches",
        ["match_key"],
        unique=True,
        postgresql_where=sa.text("match_key IS NOT NULL"),
    )

    # ── F-16 — evidence quotes (additive; legacy column kept for one release)
    op.add_column(
        "candidate_profiles",
        sa.Column(
            "evidence_quotes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )

    # ── F-20 / F-22 — richer api_usage_logs ────────────────────────────────
    op.add_column(
        "api_usage_logs",
        sa.Column("prompt_name", sa.Text(), nullable=True),
    )
    op.add_column(
        "api_usage_logs",
        sa.Column("prompt_version", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "api_usage_logs",
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("api_usage_logs", "correlation_id")
    op.drop_column("api_usage_logs", "prompt_version")
    op.drop_column("api_usage_logs", "prompt_name")

    op.drop_column("candidate_profiles", "evidence_quotes")

    op.drop_index("ix_candidate_job_matches_match_key", table_name="candidate_job_matches")
    op.drop_column("candidate_job_matches", "match_key")

    op.drop_column("applications", "ai_profiling_consented_at")
