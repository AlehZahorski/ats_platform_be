from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Job(BaseModel):
    __tablename__ = "jobs"
    __table_args__ = (
        # audit_database P1/F-34: enforce the status enum at the DB layer.
        CheckConstraint(
            "status IN ('draft','open','closed')",
            name="ck_jobs_status",
        ),
        # audit_database P2: GIN on the required_qualifications JSONB so the
        # category filter (`?| array['forklift_udt']`) hits an index instead
        # of doing a sequential scan.
        Index(
            "ix_jobs_required_qualifications_gin",
            "required_qualifications",
            postgresql_using="gin",
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    # Public URL slug. Unique per company (partial unique index). Used in
    # /jobs/{slug} URLs visible to candidates and indexed by search engines.
    slug: Mapped[str | None] = mapped_column(Text)
    department: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")

    # Classification — multi-country, multi-industry support.
    # `category` is a machine code (e.g., "nurse_registered", "truck_driver_heavy")
    # mapped to a labelled spec in frontend/features/jobs/lib/categories.ts.
    category: Mapped[str | None] = mapped_column(Text, index=True)
    # Shift system — only relevant for some categories (production, healthcare, etc.)
    # Values: one_shift | two_shift | three_shift | weekend | equivalent | null
    shift_system: Mapped[str | None] = mapped_column(Text)
    # Employment size: full | part_50 | part_75 | temporary | internship | apprenticeship
    employment_size: Mapped[str | None] = mapped_column(Text)
    # Required qualifications — list of qualification codes per category (e.g. ["forklift_udt", "sep_g1"]).
    required_qualifications: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )

    # Role content
    role_summary: Mapped[str | None] = mapped_column(Text)
    role_purpose: Mapped[str | None] = mapped_column(Text)
    role_scope: Mapped[str | None] = mapped_column(Text)
    role_deliverables: Mapped[str | None] = mapped_column(Text)
    responsibilities: Mapped[str | None] = mapped_column(Text)
    must_haves: Mapped[str | None] = mapped_column(Text)
    nice_to_haves: Mapped[str | None] = mapped_column(Text)
    tech_stack: Mapped[str | None] = mapped_column(Text)
    domain_context: Mapped[str | None] = mapped_column(Text)

    # Experience & work conditions
    seniority: Mapped[str | None] = mapped_column(Text)
    experience_min_years: Mapped[int | None] = mapped_column(Integer)
    experience_max_years: Mapped[int | None] = mapped_column(Integer)
    work_mode: Mapped[str | None] = mapped_column(Text)
    remote_constraints: Mapped[str | None] = mapped_column(Text)
    contract_type: Mapped[str | None] = mapped_column(Text)

    # Compensation
    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str | None] = mapped_column(Text)
    salary_period: Mapped[str | None] = mapped_column(Text)

    # Culture & team
    success_profile: Mapped[str | None] = mapped_column(Text)
    team_context: Mapped[str | None] = mapped_column(Text)
    reporting_to: Mapped[str | None] = mapped_column(Text)
    value_proposition: Mapped[str | None] = mapped_column(Text)
    benefits: Mapped[str | None] = mapped_column(Text)
    hiring_process: Mapped[str | None] = mapped_column(Text)

    # One-time AI starter usage — set after first successful POST /suggest.
    # Used to gate the "Suggest starters" button so it's not re-triggered.
    suggest_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    company: Mapped["Company"] = relationship(back_populates="jobs")  # noqa: F821
    applications: Mapped[list["Application"]] = relationship(back_populates="job", cascade="all, delete-orphan")  # noqa: F821
    form_template_link: Mapped["JobFormTemplate | None"] = relationship(back_populates="job", cascade="all, delete-orphan", uselist=False)  # noqa: F821
    analysis: Mapped["JobAnalysis | None"] = relationship(back_populates="job", cascade="all, delete-orphan", uselist=False)  # noqa: F821
    risk_assessment: Mapped["JobRiskAssessment | None"] = relationship(back_populates="job", cascade="all, delete-orphan", uselist=False)  # noqa: F821
    risk_items: Mapped[list["RiskItem"]] = relationship(back_populates="job", cascade="all, delete-orphan", order_by="RiskItem.order")  # noqa: F821
    mitigation_actions: Mapped[list["MitigationAction"]] = relationship(back_populates="job", cascade="all, delete-orphan", order_by="MitigationAction.order")  # noqa: F821


class JobFormTemplate(BaseModel):
    __tablename__ = "job_form_templates"

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, primary_key=True
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("form_templates.id", ondelete="RESTRICT"), nullable=False
    )

    job: Mapped["Job"] = relationship(back_populates="form_template_link")  # noqa: F821
    template: Mapped["FormTemplate"] = relationship()  # noqa: F821


class RiskItem(BaseModel):
    __tablename__ = "risk_items"

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False, default="medium")  # high | medium | low
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    job: Mapped["Job"] = relationship(back_populates="risk_items")  # noqa: F821


class MitigationAction(BaseModel):
    __tablename__ = "mitigation_actions"

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    job: Mapped["Job"] = relationship(back_populates="mitigation_actions")  # noqa: F821
