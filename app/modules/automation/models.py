from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class AutomationRule(BaseModel):
    __tablename__ = "automation_rules"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    trigger_type: Mapped[str] = mapped_column(Text, nullable=False)
    # trigger_type: stage_changed | application_created
    trigger_value: Mapped[str | None] = mapped_column(Text)
    # trigger_value: stage_id (UUID as string) for stage_changed trigger
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("email_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # relationships
    company: Mapped["Company"] = relationship()  # noqa: F821
    template: Mapped["EmailTemplate | None"] = relationship(  # noqa: F821
        back_populates="automation_rules"
    )
