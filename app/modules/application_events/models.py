from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class ApplicationEvent(BaseModel):
    __tablename__ = "application_events"

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    # event_type: stage_changed | email_sent | interview_scheduled | note_added | bulk_action
    event_value: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON)

    # relationships
    application: Mapped["Application"] = relationship()  # noqa: F821
    company: Mapped["Company | None"] = relationship()  # noqa: F821
