from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class JobAnalysis(BaseModel):
    """AI-generated attractiveness analysis for a job offer (1:1 with Job)."""

    __tablename__ = "job_analyses"

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    score: Mapped[int | None] = mapped_column(Integer)
    market_position: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    # audit_database P2/F-33: JSON → JSONB. Same reasoning as candidate_profiles —
    # binary form, indexable, `@>` containment.
    strengths: Mapped[list | None] = mapped_column(JSONB)
    improvements: Mapped[list | None] = mapped_column(JSONB)
    candidate_impact: Mapped[str | None] = mapped_column(Text)
    urgency_message: Mapped[str | None] = mapped_column(Text)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    job: Mapped["Job"] = relationship(back_populates="analysis")  # noqa: F821


class JobRiskAssessment(BaseModel):
    """AI-generated organizational risk assessment for a job offer (1:1 with Job)."""

    __tablename__ = "job_risk_assessments"
    # audit_database P1/F-34: level is a controlled enum — enforce at DB.
    __table_args__ = (
        CheckConstraint(
            "level IS NULL OR level IN ('low','medium','high')",
            name="ck_job_risk_assessments_level",
        ),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    score: Mapped[int | None] = mapped_column(Integer)
    level: Mapped[str | None] = mapped_column(Text)          # high | medium | low
    factors: Mapped[list | None] = mapped_column(JSONB)        # [{name: str, severity: str}]
    recommendations: Mapped[list | None] = mapped_column(JSONB)  # [str]
    assessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    job: Mapped["Job"] = relationship(back_populates="risk_assessment")  # noqa: F821
