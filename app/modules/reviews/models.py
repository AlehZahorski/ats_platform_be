from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class ScorecardTemplate(BaseModel):
    __tablename__ = "scorecard_templates"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    criteria: Mapped[list["ScorecardCriterion"]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="ScorecardCriterion.order_index",
    )


class ScorecardCriterion(BaseModel):
    __tablename__ = "scorecard_criteria"

    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scorecard_templates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_score: Mapped[int] = mapped_column(Integer, nullable=False, default=5)

    template: Mapped["ScorecardTemplate"] = relationship(back_populates="criteria")


class ReviewAssignment(BaseModel):
    __tablename__ = "review_assignments"
    __table_args__ = (
        UniqueConstraint("application_id", "reviewer_id", name="uq_review_assignments_application_reviewer"),
        # audit_database P1/F-34: status enum locked at DB layer.
        CheckConstraint(
            "status IN ('pending','submitted','revoked')",
            name="ck_review_assignments_status",
        ),
    )

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # audit_database P1/F-35: was ON DELETE CASCADE which deleted entire
    # reviews when a reviewer left the company → loss of audit trail. Now
    # SET NULL — the assignment row stays, the reviewer column becomes NULL,
    # and the recruiter can re-assign or mark `status='revoked'` manually.
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scorecard_templates.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    overall_comment: Mapped[str | None] = mapped_column(Text)
    recommendation: Mapped[str | None] = mapped_column(Text)

    reviewer: Mapped["User | None"] = relationship(foreign_keys=[reviewer_id])  # noqa: F821
    assigner: Mapped["User | None"] = relationship(foreign_keys=[assigned_by])  # noqa: F821
    template: Mapped["ScorecardTemplate"] = relationship()
    responses: Mapped[list["ReviewResponse"]] = relationship(
        back_populates="assignment",
        cascade="all, delete-orphan",
    )


class ReviewResponse(BaseModel):
    __tablename__ = "review_responses"
    __table_args__ = (
        UniqueConstraint("assignment_id", "criterion_id", name="uq_review_responses_assignment_criterion"),
    )

    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("review_assignments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    criterion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scorecard_criteria.id", ondelete="CASCADE"), nullable=False, index=True
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)

    assignment: Mapped["ReviewAssignment"] = relationship(back_populates="responses")
    criterion: Mapped["ScorecardCriterion"] = relationship()
