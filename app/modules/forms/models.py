from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class FormTemplate(BaseModel):
    __tablename__ = "form_templates"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)

    company: Mapped["Company"] = relationship(back_populates="form_templates")  # noqa: F821
    fields: Mapped[list["FormField"]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="FormField.order_index",
    )


class FormField(BaseModel):
    __tablename__ = "form_fields"

    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("form_templates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    field_type: Mapped[str] = mapped_column(Text, nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    options: Mapped[dict | None] = mapped_column(JSON)
    validation: Mapped[dict | None] = mapped_column(JSON)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    template: Mapped["FormTemplate"] = relationship(back_populates="fields")
