from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Candidate(BaseModel):
    """Job seeker identity. Completely separate from the recruiter-side `users`
    table — candidates log in via /api/v1/candidates/* with their own session
    cookies. This separation lets us add candidate-only features (saved jobs,
    email alerts, application history) without polluting the HR auth flow.
    """

    __tablename__ = "candidates"

    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str | None] = mapped_column(Text)
    avatar_key: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    headline: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(Text, nullable=False, default="pl")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    refresh_tokens: Mapped[list[CandidateRefreshToken]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )
    saved_jobs: Mapped[list[SavedJob]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )
    saved_companies: Mapped[list[SavedCompany]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )
    saved_searches: Mapped[list[SavedSearch]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )


class CandidateRefreshToken(BaseModel):
    __tablename__ = "candidate_refresh_tokens"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    candidate: Mapped[Candidate] = relationship(back_populates="refresh_tokens")


class SavedJob(BaseModel):
    __tablename__ = "saved_jobs"
    __table_args__ = (
        UniqueConstraint("candidate_id", "job_id", name="uq_saved_jobs_candidate_job"),
    )

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )

    candidate: Mapped[Candidate] = relationship(back_populates="saved_jobs")


class SavedCompany(BaseModel):
    """DB-backed 'Obserwuj firmę' for logged-in candidates.

    Anonymous follows live in localStorage on the client. The same UI hook
    abstracts both stores (see useSavedCompaniesSet on the frontend).
    """

    __tablename__ = "saved_companies"
    __table_args__ = (
        UniqueConstraint("candidate_id", "company_id", name="uq_saved_companies_candidate_company"),
    )

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )

    candidate: Mapped[Candidate] = relationship(back_populates="saved_companies")


class SavedSearch(BaseModel):
    """Persisted filter set + optional email alert opt-in. The `query` JSONB
    holds whatever filter shape the frontend assembles (categories, work modes,
    salary range, keywords). Kept opaque on purpose so we don't need a migration
    every time a new filter is added.
    """

    __tablename__ = "saved_searches"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    query: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    notify_email: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    candidate: Mapped[Candidate] = relationship(back_populates="saved_searches")


class SearchLog(BaseModel):
    """Single search event — anonymous (candidate_id NULL) or attributed.

    Aggregated nightly to drive the "popular" chip row on the homepage.
    """

    __tablename__ = "search_logs"

    candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="SET NULL"), nullable=True
    )
    query_text: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text, index=True)
    location: Mapped[str | None] = mapped_column(Text)
