from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSON, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Application(BaseModel):
    __tablename__ = "applications"

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    first_name: Mapped[str] = mapped_column(Text, nullable=False)
    last_name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    normalized_email: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(Text)
    normalized_phone: Mapped[str | None] = mapped_column(Text, index=True)
    cv_url: Mapped[str | None] = mapped_column(Text)
    stage_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pipeline_stages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    public_token: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)

    # v2 fields
    source: Mapped[str | None] = mapped_column(Text, index=True)
    # source: direct | linkedin | referral | website | other
    language: Mapped[str] = mapped_column(Text, nullable=False, default="en")
    data_retention_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    # F-02: explicit consent for AI profiling. NULL = no consent → the backend
    # redacts PII (email, phone) before sending the CV to Anthropic.
    ai_profiling_consented_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # relationships
    job: Mapped["Job"] = relationship(back_populates="applications")  # noqa: F821
    stage: Mapped["PipelineStage | None"] = relationship(back_populates="applications")  # noqa: F821
    answers: Mapped[list["ApplicationAnswer"]] = relationship(back_populates="application", cascade="all, delete-orphan")
    stage_history: Mapped[list["ApplicationStageHistory"]] = relationship(back_populates="application", cascade="all, delete-orphan")  # noqa: F821
    notes: Mapped[list["Note"]] = relationship(back_populates="application", cascade="all, delete-orphan")  # noqa: F821
    scores: Mapped[list["CandidateScore"]] = relationship(back_populates="application", cascade="all, delete-orphan")  # noqa: F821
    tag_links: Mapped[list["ApplicationTag"]] = relationship(back_populates="application", cascade="all, delete-orphan")  # noqa: F821
    duplicate_links_from: Mapped[list["ApplicationDuplicateLink"]] = relationship(
        foreign_keys="ApplicationDuplicateLink.source_application_id",
        back_populates="source_application",
        cascade="all, delete-orphan",
    )
    duplicate_links_to: Mapped[list["ApplicationDuplicateLink"]] = relationship(
        foreign_keys="ApplicationDuplicateLink.duplicate_application_id",
        back_populates="duplicate_application",
        cascade="all, delete-orphan",
    )
    cv_parse_jobs: Mapped[list["CVParseJob"]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="desc(CVParseJob.created_at)",
    )
    candidate_profile: Mapped["CandidateProfile | None"] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        uselist=False,
    )


class ApplicationAnswer(BaseModel):
    __tablename__ = "application_answers"

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("form_fields.id", ondelete="CASCADE"), nullable=False, index=True
    )
    value: Mapped[dict] = mapped_column(JSON, nullable=False)

    application: Mapped["Application"] = relationship(back_populates="answers")
    field: Mapped["FormField"] = relationship()  # noqa: F821


class CandidateScore(BaseModel):
    __tablename__ = "candidate_scores"

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recruiter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    communication: Mapped[int | None] = mapped_column()
    technical: Mapped[int | None] = mapped_column()
    culture_fit: Mapped[int | None] = mapped_column()

    application: Mapped["Application"] = relationship(back_populates="scores")
    recruiter: Mapped["User | None"] = relationship()  # noqa: F821


class ApplicationDuplicateLink(BaseModel):
    __tablename__ = "application_duplicate_links"

    source_application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    duplicate_application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    match_reasons: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    source_application: Mapped["Application"] = relationship(
        foreign_keys=[source_application_id],
        back_populates="duplicate_links_from",
    )
    duplicate_application: Mapped["Application"] = relationship(
        foreign_keys=[duplicate_application_id],
        back_populates="duplicate_links_to",
    )


class CVParseJob(BaseModel):
    __tablename__ = "cv_parse_jobs"

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cv_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="queued", index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    raw_text: Mapped[str | None] = mapped_column(Text)
    raw_result: Mapped[dict | None] = mapped_column(JSON)
    normalized_result: Mapped[dict | None] = mapped_column(JSON)
    parser_version: Mapped[str] = mapped_column(Text, nullable=False, default="v1")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # LLM metadata
    llm_model: Mapped[str | None] = mapped_column(Text)
    token_usage: Mapped[dict | None] = mapped_column(JSON)
    language: Mapped[str | None] = mapped_column(Text)

    application: Mapped["Application"] = relationship(back_populates="cv_parse_jobs")


class CandidateProfile(BaseModel):
    __tablename__ = "candidate_profiles"

    __table_args__ = (
        Index("ix_candidate_profiles_technical_skills", "technical_skills", postgresql_using="gin"),
        Index("ix_candidate_profiles_languages", "languages", postgresql_using="gin"),
    )

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    # v1 fields (regex parser) — kept for backwards compatibility
    headline: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    skills: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    experience: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    education: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    parsing_status: Mapped[str] = mapped_column(Text, nullable=False, default="idle", index=True)
    parsing_error: Mapped[str | None] = mapped_column(Text)
    last_parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # v2 fields (LLM enrichment)
    parser_version: Mapped[str] = mapped_column(Text, nullable=False, default="v1-regex", index=True)
    personal_summary: Mapped[str | None] = mapped_column(Text)
    executive_summary: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    linkedin_url: Mapped[str | None] = mapped_column(Text)
    github_url: Mapped[str | None] = mapped_column(Text)
    technical_skills: Mapped[list[dict] | None] = mapped_column(JSONB)
    soft_skills: Mapped[list[dict] | None] = mapped_column(JSON)
    languages: Mapped[list[dict] | None] = mapped_column(JSONB)
    certifications: Mapped[list[dict] | None] = mapped_column(JSON)
    hobbies: Mapped[list[str] | None] = mapped_column(JSON)
    volunteering: Mapped[list[str] | None] = mapped_column(JSON)
    total_experience_years: Mapped[float | None] = mapped_column(Float)
    seniority_estimate: Mapped[str | None] = mapped_column(Text, index=True)
    strengths: Mapped[list[str] | None] = mapped_column(JSON)
    red_flags: Mapped[list[str] | None] = mapped_column(JSON)
    # F-16: legacy column. Kept readable for one release for the existing UI;
    # new writes go to `evidence_quotes` instead. Dropped in a follow-up
    # migration after the frontend has switched.
    personality_signals: Mapped[dict | None] = mapped_column(JSON)
    evidence_quotes: Mapped[list[dict] | None] = mapped_column(JSONB)
    culture_fit_notes: Mapped[str | None] = mapped_column(Text)

    application: Mapped["Application"] = relationship(back_populates="candidate_profile")
    job_matches: Mapped[list["CandidateJobMatch"]] = relationship(
        back_populates="candidate_profile",
        cascade="all, delete-orphan",
        order_by="desc(CandidateJobMatch.created_at)",
    )


class CandidateJobMatch(BaseModel):
    __tablename__ = "candidate_job_matches"

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    candidate_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    match_score: Mapped[int | None] = mapped_column(Integer, index=True)
    fit_score: Mapped[int | None] = mapped_column(Integer, index=True)
    reasoning: Mapped[str | None] = mapped_column(Text)
    strengths_match: Mapped[list[str] | None] = mapped_column(JSON)
    gaps: Mapped[list[str] | None] = mapped_column(JSON)
    recommendation: Mapped[str | None] = mapped_column(Text)
    llm_model: Mapped[str | None] = mapped_column(Text)
    token_usage: Mapped[dict | None] = mapped_column(JSON)
    # F-09: idempotency key — sha256(candidate_profile_id|job_id|profile_signature).
    # A second match call with the same key short-circuits (no Anthropic call).
    match_key: Mapped[str | None] = mapped_column(Text, index=True)

    candidate_profile: Mapped["CandidateProfile"] = relationship(back_populates="job_matches")
    application: Mapped["Application"] = relationship()
    job: Mapped["Job"] = relationship()  # noqa: F821


class ApiUsageLog(BaseModel):
    __tablename__ = "api_usage_logs"

    __table_args__ = (
        Index("ix_api_usage_logs_company_created", "company_id", "created_at"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    operation: Mapped[str] = mapped_column(Text, nullable=False)
    llm_model: Mapped[str] = mapped_column(Text, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # F-20: which prompt produced the call (filename, no .txt) and its content
    # hash. Used by the LLM-usage dashboard to group by template version when
    # we tune prompts.
    prompt_name: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    # F-22: request-scoped UUID so a log entry can be traced back to a single
    # background job / API request.
    correlation_id: Mapped[str | None] = mapped_column(Text)

    company: Mapped["Company"] = relationship()  # noqa: F821
