"""Database performance hardening — audit_database_2026_05_28

Targets the high-impact items from the database audit:

Composite indexes (eliminate sort-after-scan on hot paths):
  - applications(job_id, created_at DESC)         — list per job
  - applications(stage_id, created_at DESC)       — kanban per stage
  - applications(job_id, stage_id)                — kanban per job
  - applications(job_id, normalized_email)        — fast dedup-check at apply
  - application_stage_history(application_id, changed_at DESC) — timeline
  - audit_logs(company_id, created_at DESC)       — admin log listing
  - audit_logs(company_id, entity_type, entity_id) — entity drilldown
  - audit_logs(company_id, action)                — action reports
  - refresh_tokens(user_id, revoked, expires_at)  — session cleanup

Trigram GIN for fuzzy/contains search (replaces ILIKE full-scan):
  - pg_trgm extension
  - GIN trgm on applications(first_name, last_name, email)

JSON → JSONB upgrade (B-tree-comparable + supports @>, ?| operators):
  - candidate_profiles.soft_skills / certifications / hobbies / volunteering
    / strengths / red_flags / personality_signals
  - audit_logs.metadata
  - job_analyses.strengths / improvements
  - job_risk_assessments.factors / recommendations

New GINs after the JSONB upgrade:
  - jobs.required_qualifications  (already JSONB, just lacked the GIN)
  - audit_logs.metadata
  - candidate_profiles.soft_skills
  - candidate_profiles.certifications

CHECK constraints (enforce enums at the DB layer, not just Pydantic):
  - users.role IN ('owner','recruiter','manager')
  - jobs.status IN ('draft','open','closed')
  - candidate_scores.{communication,technical,culture_fit} BETWEEN 1 AND 5
  - review_assignments.status IN ('pending','submitted','revoked')
  - job_risk_assessments.level IN ('low','medium','high')
  - candidate_job_matches.recommendation IN ('top_candidate','consider','not_a_match')
  - candidate_job_matches.match_status IN ('completed','pending','llm_disabled','llm_failed')

FK fix:
  - review_assignments.reviewer_id ON DELETE CASCADE → SET NULL (P1, audit)
    + make column nullable. Revoked reviews keep history.

Drop redundant single-column indexes (they duplicate an existing UNIQUE):
  - applications.email (idx_applications_email)
    Kept: normalized_email index (actually used by dedup).

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-05-28 16:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ───────────────────────────────────────────────────────────────────────────
# Composite indexes — high-impact, no data rewrite.
# ───────────────────────────────────────────────────────────────────────────

_COMPOSITE_INDEXES = [
    # (name, table, columns, kwargs)
    ("ix_applications_job_created", "applications",
     [sa.text("job_id"), sa.text("created_at DESC")], {}),
    ("ix_applications_stage_created", "applications",
     [sa.text("stage_id"), sa.text("created_at DESC")], {}),
    ("ix_applications_job_stage", "applications",
     ["job_id", "stage_id"], {}),
    ("ix_applications_job_normalized_email", "applications",
     ["job_id", "normalized_email"], {}),
    ("ix_application_stage_history_app_changed", "application_stage_history",
     [sa.text("application_id"), sa.text("changed_at DESC")], {}),
    ("ix_audit_logs_company_created", "audit_logs",
     [sa.text("company_id"), sa.text("created_at DESC")], {}),
    ("ix_audit_logs_company_entity", "audit_logs",
     ["company_id", "entity_type", "entity_id"], {}),
    ("ix_audit_logs_company_action", "audit_logs",
     ["company_id", "action"], {}),
    ("ix_refresh_tokens_user_revoked_expires", "refresh_tokens",
     ["user_id", "revoked", "expires_at"], {}),
]


def upgrade() -> None:
    # ── pg_trgm extension (one-time) ────────────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # ── Composite B-tree indexes ────────────────────────────────────────
    for name, table, cols, kwargs in _COMPOSITE_INDEXES:
        # Use raw SQL for DESC + IF NOT EXISTS guard (re-running locally is safer).
        col_sql = ", ".join(
            c.text if hasattr(c, "text") else c for c in cols
        )
        op.execute(
            f'CREATE INDEX IF NOT EXISTS "{name}" '
            f'ON {table} ({col_sql})'
        )

    # ── Trigram GIN — eliminates the full-scan on ILIKE '%term%' ────────
    op.execute(
        'CREATE INDEX IF NOT EXISTS "ix_applications_first_name_trgm" '
        'ON applications USING gin (first_name gin_trgm_ops)'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS "ix_applications_last_name_trgm" '
        'ON applications USING gin (last_name gin_trgm_ops)'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS "ix_applications_email_trgm" '
        'ON applications USING gin (email gin_trgm_ops)'
    )

    # ── JSON → JSONB conversions (USING col::jsonb) ──────────────────────
    # SQLAlchemy's alter_column with postgresql_using handles it cleanly.
    op.execute(
        "ALTER TABLE candidate_profiles "
        "ALTER COLUMN soft_skills TYPE JSONB USING soft_skills::jsonb"
    )
    op.execute(
        "ALTER TABLE candidate_profiles "
        "ALTER COLUMN certifications TYPE JSONB USING certifications::jsonb"
    )
    op.execute(
        "ALTER TABLE candidate_profiles "
        "ALTER COLUMN hobbies TYPE JSONB USING hobbies::jsonb"
    )
    op.execute(
        "ALTER TABLE candidate_profiles "
        "ALTER COLUMN volunteering TYPE JSONB USING volunteering::jsonb"
    )
    op.execute(
        "ALTER TABLE candidate_profiles "
        "ALTER COLUMN strengths TYPE JSONB USING strengths::jsonb"
    )
    op.execute(
        "ALTER TABLE candidate_profiles "
        "ALTER COLUMN red_flags TYPE JSONB USING red_flags::jsonb"
    )
    op.execute(
        "ALTER TABLE candidate_profiles "
        "ALTER COLUMN personality_signals TYPE JSONB USING personality_signals::jsonb"
    )
    op.execute(
        'ALTER TABLE audit_logs '
        'ALTER COLUMN metadata TYPE JSONB USING metadata::jsonb'
    )
    op.execute(
        "ALTER TABLE job_analyses "
        "ALTER COLUMN strengths TYPE JSONB USING strengths::jsonb"
    )
    op.execute(
        "ALTER TABLE job_analyses "
        "ALTER COLUMN improvements TYPE JSONB USING improvements::jsonb"
    )
    op.execute(
        "ALTER TABLE job_risk_assessments "
        "ALTER COLUMN factors TYPE JSONB USING factors::jsonb"
    )
    op.execute(
        "ALTER TABLE job_risk_assessments "
        "ALTER COLUMN recommendations TYPE JSONB USING recommendations::jsonb"
    )

    # ── GIN indexes on the new JSONB columns + jobs.required_qualifications
    op.execute(
        'CREATE INDEX IF NOT EXISTS "ix_jobs_required_qualifications_gin" '
        "ON jobs USING gin (required_qualifications)"
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS "ix_audit_logs_metadata_gin" '
        "ON audit_logs USING gin (metadata)"
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS "ix_candidate_profiles_soft_skills_gin" '
        "ON candidate_profiles USING gin (soft_skills)"
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS "ix_candidate_profiles_certifications_gin" '
        "ON candidate_profiles USING gin (certifications)"
    )

    # ── review_assignments.reviewer_id: CASCADE → SET NULL + nullable ────
    op.execute(
        "ALTER TABLE review_assignments "
        "DROP CONSTRAINT IF EXISTS review_assignments_reviewer_id_fkey"
    )
    op.alter_column(
        "review_assignments",
        "reviewer_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.create_foreign_key(
        "review_assignments_reviewer_id_fkey",
        "review_assignments",
        "users",
        ["reviewer_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ── CHECK constraints — enforce enums at the DB layer ───────────────
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN ('owner','recruiter','manager')",
    )
    op.create_check_constraint(
        "ck_jobs_status",
        "jobs",
        "status IN ('draft','open','closed')",
    )
    op.create_check_constraint(
        "ck_candidate_scores_communication",
        "candidate_scores",
        "communication IS NULL OR (communication BETWEEN 1 AND 5)",
    )
    op.create_check_constraint(
        "ck_candidate_scores_technical",
        "candidate_scores",
        "technical IS NULL OR (technical BETWEEN 1 AND 5)",
    )
    op.create_check_constraint(
        "ck_candidate_scores_culture_fit",
        "candidate_scores",
        "culture_fit IS NULL OR (culture_fit BETWEEN 1 AND 5)",
    )
    op.create_check_constraint(
        "ck_review_assignments_status",
        "review_assignments",
        "status IN ('pending','submitted','revoked')",
    )
    op.create_check_constraint(
        "ck_job_risk_assessments_level",
        "job_risk_assessments",
        "level IS NULL OR level IN ('low','medium','high')",
    )
    op.create_check_constraint(
        "ck_candidate_job_matches_recommendation",
        "candidate_job_matches",
        "recommendation IS NULL OR recommendation IN "
        "('top_candidate','consider','not_a_match')",
    )
    op.create_check_constraint(
        "ck_candidate_job_matches_status",
        "candidate_job_matches",
        "match_status IN ('completed','pending','llm_disabled','llm_failed')",
    )

    # ── Drop redundant indexes — duplicate of existing UNIQUE constraint ─
    # `applications.email` index is held alongside the (better) normalized_email
    # index. Search uses ILIKE which now has the trigram GIN; equality match
    # uses normalized_email. The plain `email` btree is therefore unused.
    op.execute('DROP INDEX IF EXISTS "ix_applications_email"')


def downgrade() -> None:
    # CHECKs ────────────────────────────────────────────────────────────
    for name, table in [
        ("ck_candidate_job_matches_status", "candidate_job_matches"),
        ("ck_candidate_job_matches_recommendation", "candidate_job_matches"),
        ("ck_job_risk_assessments_level", "job_risk_assessments"),
        ("ck_review_assignments_status", "review_assignments"),
        ("ck_candidate_scores_culture_fit", "candidate_scores"),
        ("ck_candidate_scores_technical", "candidate_scores"),
        ("ck_candidate_scores_communication", "candidate_scores"),
        ("ck_jobs_status", "jobs"),
        ("ck_users_role", "users"),
    ]:
        op.execute(f'ALTER TABLE {table} DROP CONSTRAINT IF EXISTS "{name}"')

    # review_assignments FK → back to CASCADE + NOT NULL ───────────────
    op.execute(
        "ALTER TABLE review_assignments "
        "DROP CONSTRAINT IF EXISTS review_assignments_reviewer_id_fkey"
    )
    # Best-effort: leave existing NULLs in place — downgrade does not back-fill.
    op.create_foreign_key(
        "review_assignments_reviewer_id_fkey",
        "review_assignments",
        "users",
        ["reviewer_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # GIN indexes added in upgrade ────────────────────────────────────
    for name in [
        "ix_candidate_profiles_certifications_gin",
        "ix_candidate_profiles_soft_skills_gin",
        "ix_audit_logs_metadata_gin",
        "ix_jobs_required_qualifications_gin",
        "ix_applications_email_trgm",
        "ix_applications_last_name_trgm",
        "ix_applications_first_name_trgm",
    ]:
        op.execute(f'DROP INDEX IF EXISTS "{name}"')

    # JSONB → JSON ─────────────────────────────────────────────────────
    op.execute(
        "ALTER TABLE job_risk_assessments "
        "ALTER COLUMN recommendations TYPE JSON USING recommendations::json"
    )
    op.execute(
        "ALTER TABLE job_risk_assessments "
        "ALTER COLUMN factors TYPE JSON USING factors::json"
    )
    op.execute(
        "ALTER TABLE job_analyses "
        "ALTER COLUMN improvements TYPE JSON USING improvements::json"
    )
    op.execute(
        "ALTER TABLE job_analyses "
        "ALTER COLUMN strengths TYPE JSON USING strengths::json"
    )
    op.execute(
        "ALTER TABLE audit_logs "
        "ALTER COLUMN metadata TYPE JSON USING metadata::json"
    )
    for col in [
        "personality_signals", "red_flags", "strengths",
        "volunteering", "hobbies", "certifications", "soft_skills",
    ]:
        op.execute(
            f"ALTER TABLE candidate_profiles "
            f"ALTER COLUMN {col} TYPE JSON USING {col}::json"
        )

    # Composite indexes ───────────────────────────────────────────────
    for name, _, _, _ in reversed(_COMPOSITE_INDEXES):
        op.execute(f'DROP INDEX IF EXISTS "{name}"')

    # Restore the (now unused) email btree so downgrade is symmetrical.
    op.execute(
        'CREATE INDEX IF NOT EXISTS "ix_applications_email" '
        'ON applications (email)'
    )

    # Extension left in place — it's harmless and other tenants may rely on it.
