from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Job(BaseModel):
    __tablename__ = "jobs"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    department: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")

    # relationships
    company: Mapped["Company"] = relationship(back_populates="jobs")  # noqa: F821
    applications: Mapped[list["Application"]] = relationship(back_populates="job", cascade="all, delete-orphan")  # noqa: F821
    form_template_link: Mapped["JobFormTemplate | None"] = relationship(back_populates="job", cascade="all, delete-orphan", uselist=False)  # noqa: F821


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
