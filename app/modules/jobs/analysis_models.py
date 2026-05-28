from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Text
from sqlalchemy.dialects.postgresql import UUID
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
    strengths: Mapped[list | None] = mapped_column(JSON)
    improvements: Mapped[list | None] = mapped_column(JSON)
    candidate_impact: Mapped[str | None] = mapped_column(Text)
    urgency_message: Mapped[str | None] = mapped_column(Text)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    job: Mapped["Job"] = relationship(back_populates="analysis")  # noqa: F821


class JobRiskAssessment(BaseModel):
    """AI-generated organizational risk assessment for a job offer (1:1 with Job)."""

    __tablename__ = "job_risk_assessments"

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    score: Mapped[int | None] = mapped_column(Integer)
    level: Mapped[str | None] = mapped_column(Text)          # high | medium | low
    factors: Mapped[list | None] = mapped_column(JSON)        # [{name: str, severity: str}]
    recommendations: Mapped[list | None] = mapped_column(JSON)  # [str]
    assessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    job: Mapped["Job"] = relationship(back_populates="risk_assessment")  # noqa: F821
