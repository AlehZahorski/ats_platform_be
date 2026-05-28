"""companies public profile fields + saved_companies

Adds the columns that back the public /firmy listing and /firmy/{slug} profile:
  - slug (unique) — public URL, generated from name on first profile save
  - logo_url, banner_url — uploads (filled in etap 2, nullable on MVP)
  - tagline, description — short + long blurb
  - industry, employee_count, hq_location, founded_year, website
  - remote_percentage — drives the "85% pracuje zdalnie" KPI
  - JSONB: tech_stack, how_we_work, benefits, recruitment_process, timeline,
    faq, gallery — every section the profile renders. All optional; empty
    sections are hidden on the public page.

Also creates saved_companies — DB-backed "Obserwuj firmę" for logged-in
candidates (mirrors saved_jobs). Anonymous follows stay in localStorage.

Revision ID: f3a4b5c6d7e8
Revises: d6e7f8a9b0c1
Create Date: 2026-05-24 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, None] = "d6e7f8a9b0c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── companies: public profile fields ─────────────────────────────────
    op.add_column("companies", sa.Column("slug", sa.Text(), nullable=True))
    op.create_index("uq_companies_slug", "companies", ["slug"], unique=True, postgresql_where=sa.text("slug IS NOT NULL"))

    op.add_column("companies", sa.Column("logo_url", sa.Text(), nullable=True))
    op.add_column("companies", sa.Column("banner_url", sa.Text(), nullable=True))
    op.add_column("companies", sa.Column("tagline", sa.Text(), nullable=True))
    op.add_column("companies", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("companies", sa.Column("industry", sa.Text(), nullable=True))
    op.add_column("companies", sa.Column("employee_count", sa.Integer(), nullable=True))
    op.add_column("companies", sa.Column("hq_location", sa.Text(), nullable=True))
    op.add_column("companies", sa.Column("founded_year", sa.Integer(), nullable=True))
    op.add_column("companies", sa.Column("website", sa.Text(), nullable=True))
    op.add_column("companies", sa.Column("remote_percentage", sa.Integer(), nullable=True))

    # JSONB sections — each defaults to [] so the model can iterate without a
    # null check. The frontend treats "empty array" the same as "missing" and
    # hides the section completely.
    for col in (
        "tech_stack",
        "how_we_work",
        "benefits",
        "recruitment_process",
        "timeline",
        "faq",
        "gallery",
    ):
        op.add_column(
            "companies",
            sa.Column(col, postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        )

    # Help the public list query: filter by industry / verified_only, search by name.
    op.create_index("ix_companies_industry", "companies", ["industry"])
    op.create_index("ix_companies_is_verified", "companies", ["is_verified"])

    # ── saved_companies: DB-backed follow for logged-in candidates ───────
    op.create_table(
        "saved_companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("candidate_id", "company_id", name="uq_saved_companies_candidate_company"),
    )
    op.create_index("ix_saved_companies_candidate_id", "saved_companies", ["candidate_id"])


def downgrade() -> None:
    op.drop_index("ix_saved_companies_candidate_id", table_name="saved_companies")
    op.drop_table("saved_companies")

    op.drop_index("ix_companies_is_verified", table_name="companies")
    op.drop_index("ix_companies_industry", table_name="companies")

    for col in (
        "gallery",
        "faq",
        "timeline",
        "recruitment_process",
        "benefits",
        "how_we_work",
        "tech_stack",
        "remote_percentage",
        "website",
        "founded_year",
        "hq_location",
        "employee_count",
        "industry",
        "description",
        "tagline",
        "banner_url",
        "logo_url",
    ):
        op.drop_column("companies", col)

    op.drop_index("uq_companies_slug", table_name="companies")
    op.drop_column("companies", "slug")
