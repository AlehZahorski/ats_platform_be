from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Company(BaseModel):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    # Verified by platform admin (manual approval after CEIDG/KRS check).
    # Displayed as a green tick on the public job board next to the company name.
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    # ── Public profile (/firmy/{slug}) ───────────────────────────────────
    # Stable URL slug. Filled when the company first saves a public profile.
    slug: Mapped[str | None] = mapped_column(Text, nullable=True)
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    banner_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    tagline: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    industry: Mapped[str | None] = mapped_column(Text, nullable=True)
    employee_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hq_location: Mapped[str | None] = mapped_column(Text, nullable=True)
    founded_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    remote_percentage: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # JSONB sections. Empty array == "no content" → frontend hides the whole
    # section rather than rendering a placeholder.
    tech_stack: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    how_we_work: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    benefits: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    recruitment_process: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    timeline: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    faq: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    gallery: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")

    # relationships
    users: Mapped[list["User"]] = relationship(back_populates="company", cascade="all, delete-orphan")  # noqa: F821
    jobs: Mapped[list["Job"]] = relationship(back_populates="company", cascade="all, delete-orphan")  # noqa: F821
    form_templates: Mapped[list["FormTemplate"]] = relationship(back_populates="company", cascade="all, delete-orphan")  # noqa: F821
    tags: Mapped[list["Tag"]] = relationship(back_populates="company", cascade="all, delete-orphan")  # noqa: F821
