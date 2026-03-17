from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class EmailTemplate(BaseModel):
    __tablename__ = "email_templates"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    # types: application_received | interview_invite | rejection | offer | custom
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(Text, nullable=False, default="en")
    variables: Mapped[dict | None] = mapped_column(JSON)
    # variables stores list of available variable names e.g. {"vars": ["candidate_name", "job_title"]}

    # relationships
    company: Mapped["Company"] = relationship()  # noqa: F821
    automation_rules: Mapped[list["AutomationRule"]] = relationship(  # noqa: F821
        back_populates="template"
    )
