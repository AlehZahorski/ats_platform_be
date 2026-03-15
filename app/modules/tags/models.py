from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Tag(BaseModel):
    __tablename__ = "tags"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)

    company: Mapped["Company"] = relationship(back_populates="tags")  # noqa: F821
    application_links: Mapped[list["ApplicationTag"]] = relationship(back_populates="tag", cascade="all, delete-orphan")


class ApplicationTag(BaseModel):
    __tablename__ = "application_tags"

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE"), nullable=False, primary_key=True, index=True
    )

    application: Mapped["Application"] = relationship(back_populates="tag_links")  # noqa: F821
    tag: Mapped["Tag"] = relationship(back_populates="application_links")
