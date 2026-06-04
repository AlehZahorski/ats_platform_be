from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Note(BaseModel):
    __tablename__ = "notes"

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # RESERVED (Faza 2): there is currently NO candidate-facing read path for
    # notes — both /notes endpoints require an authenticated HR user, and the
    # public /track/{token} response (ApplicationTrackingRead) never includes
    # notes. This flag is kept for a future candidate-visible-notes feature; if
    # such a path is added it MUST filter on visible_to_candidate. Guarded by
    # tests/test_data_consistency.py::test_track_does_not_leak_notes.
    visible_to_candidate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    application: Mapped[Application] = relationship(back_populates="notes")  # noqa: F821
    author: Mapped[User | None] = relationship()  # noqa: F821
