from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class PipelineStage(BaseModel):
    __tablename__ = "pipeline_stages"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)

    applications: Mapped[list["Application"]] = relationship(back_populates="stage")  # noqa: F821
    history: Mapped[list["ApplicationStageHistory"]] = relationship(back_populates="stage")


class ApplicationStageHistory(BaseModel):
    __tablename__ = "application_stage_history"

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pipeline_stages.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    changed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    application: Mapped["Application"] = relationship(back_populates="stage_history")  # noqa: F821
    stage: Mapped["PipelineStage"] = relationship(back_populates="history")
    changer: Mapped["User | None"] = relationship()  # noqa: F821
