from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from app.core.database import Base


class Consent(BaseModel):
    __tablename__ = "consents"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(Text, nullable=False, default="en")
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # relationships
    company: Mapped["Company"] = relationship()  # noqa: F821
    application_consents: Mapped[list["ApplicationConsent"]] = relationship(
        back_populates="consent", cascade="all, delete-orphan"
    )


class ApplicationConsent(Base):
    """Many-to-many: applications ↔ consents with acceptance data."""

    __tablename__ = "application_consents"

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    )
    consent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("consents.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
        index=True,
    )
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # relationships
    application: Mapped["Application"] = relationship()  # noqa: F821
    consent: Mapped["Consent"] = relationship(back_populates="application_consents")
