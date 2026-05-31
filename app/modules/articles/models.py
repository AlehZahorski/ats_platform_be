from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Article(BaseModel):
    """Poradnik / Opinie-firm article. HTML body stored verbatim —
    rendered with dangerouslySetInnerHTML on the frontend, same
    pattern as job description/responsibilities elsewhere.

    Two flavours, distinguished by `type`:
      • 'editorial' — admin-authored, on /poradnik. company_id is NULL.
      • 'company'   — written by a verified company, on /opinie-firm.
        company_id points at the owning company. Admin can still moderate.

    Author info is snapshotted (name/role/avatar) so deleting an account
    or unlinking a company doesn't blank out historical bylines.
    """

    __tablename__ = "articles"

    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    cover_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    is_featured: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_published: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    # Promotion lifts a type='company' article into the editorial /poradnik
    # feed. Admin-only toggle; companies can't self-promote.
    is_promoted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    promoted_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Discriminator + ownership.
    type: Mapped[str] = mapped_column(
        Text, nullable=False, default="editorial", server_default="editorial", index=True
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Author snapshot. For 'company' articles this is the person inside
    # the company who wrote it (CTO / Head of X). For 'editorial' it's
    # the admin byline ("Jan Kowalski, Senior Tech Recruiter").
    author_name: Mapped[str] = mapped_column(Text, nullable=False)
    author_role: Mapped[str | None] = mapped_column(Text, nullable=True)
    author_avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    author_email: Mapped[str | None] = mapped_column(Text, nullable=True)

    read_time_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company: Mapped[Company] = relationship(  # noqa: F821
        "Company",
        foreign_keys=[company_id],
        lazy="joined",
    )


class NewsletterSubscriber(BaseModel):
    """Email list collected from the Poradnik newsletter widget.

    No sending pipeline yet — this just preserves the addresses for a
    future broadcast tool. The `source` column lets us tell where each
    subscription came from (currently always 'poradnik').
    """

    __tablename__ = "newsletter_subscribers"

    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    subscribed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    unsubscribed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
