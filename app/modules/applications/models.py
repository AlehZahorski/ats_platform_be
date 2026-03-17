from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
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
    phone: Mapped[str | None] = mapped_column(Text)
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

    # relationships
    job: Mapped["Job"] = relationship(back_populates="applications")  # noqa: F821
    stage: Mapped["PipelineStage | None"] = relationship(back_populates="applications")  # noqa: F821
    answers: Mapped[list["ApplicationAnswer"]] = relationship(back_populates="application", cascade="all, delete-orphan")
    stage_history: Mapped[list["ApplicationStageHistory"]] = relationship(back_populates="application", cascade="all, delete-orphan")  # noqa: F821
    notes: Mapped[list["Note"]] = relationship(back_populates="application", cascade="all, delete-orphan")  # noqa: F821
    scores: Mapped[list["CandidateScore"]] = relationship(back_populates="application", cascade="all, delete-orphan")  # noqa: F821
    tag_links: Mapped[list["ApplicationTag"]] = relationship(back_populates="application", cascade="all, delete-orphan")  # noqa: F821


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
