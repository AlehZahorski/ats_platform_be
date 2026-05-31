from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Slug is the public URL fragment. Lowercase letters, digits, hyphens.
# 3–60 chars so /firmy/{slug} stays sane and SEO-friendly.
SLUG_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,58}[a-z0-9])?$")


class CompanyBase(BaseModel):
    name: str


class CompanyCreate(CompanyBase):
    pass


# ─────────────────────────────────────────────────────────────────────
# Section payloads — every JSONB section has a strict pydantic shape
# so the dashboard editor and the public renderer agree on field names.
# ─────────────────────────────────────────────────────────────────────


class HowWeWorkCard(BaseModel):
    icon: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=240)


class RecruitmentStep(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    duration: str | None = Field(default=None, max_length=40)


class FaqEntry(BaseModel):
    question: str = Field(min_length=1, max_length=240)
    answer: str = Field(min_length=1, max_length=2000)


class TimelineEntry(BaseModel):
    year: int = Field(ge=1800, le=2100)
    title: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=240)


class GalleryItem(BaseModel):
    url: str
    caption: str | None = Field(default=None, max_length=200)


class CompanyUpdate(BaseModel):
    """Owner-side profile editor payload. Every field is optional so the
    dashboard can save one section at a time without re-sending the rest.

    `slug` policy: once set, it's immutable here — the public URL must be
    stable. To change slug a platform admin has to do it directly (out of
    scope for MVP). The service layer enforces this; the schema only does
    format validation.
    """

    name: str | None = Field(default=None, min_length=1, max_length=200)
    slug: str | None = Field(default=None)
    logo_url: str | None = None
    banner_url: str | None = None
    tagline: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    industry: str | None = Field(default=None, max_length=80)
    employee_count: int | None = Field(default=None, ge=1, le=1_000_000)
    hq_location: str | None = Field(default=None, max_length=200)
    founded_year: int | None = Field(default=None, ge=1800, le=2100)
    website: str | None = Field(default=None, max_length=400)
    remote_percentage: int | None = Field(default=None, ge=0, le=100)

    tech_stack: list[str] | None = None
    how_we_work: list[HowWeWorkCard] | None = None
    benefits: list[str] | None = None
    recruitment_process: list[RecruitmentStep] | None = None
    timeline: list[TimelineEntry] | None = None
    faq: list[FaqEntry] | None = None
    gallery: list[GalleryItem] | None = None

    @field_validator("slug")
    @classmethod
    def _validate_slug(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip().lower()
        if not SLUG_PATTERN.match(v):
            raise ValueError(
                "Slug może zawierać tylko małe litery, cyfry i myślniki (3–60 znaków)."
            )
        return v


class CompanyRead(CompanyBase):
    """Authenticated 'my company' view. Includes everything the dashboard
    editor needs to round-trip. Public never sees this shape — public reads
    go through CompanyPublicDetail.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    is_verified: bool
    created_at: datetime

    slug: str | None
    logo_url: str | None
    banner_url: str | None
    tagline: str | None
    description: str | None
    industry: str | None
    employee_count: int | None
    hq_location: str | None
    founded_year: int | None
    website: str | None
    remote_percentage: int | None

    tech_stack: list[Any] = []
    how_we_work: list[Any] = []
    benefits: list[Any] = []
    recruitment_process: list[Any] = []
    timeline: list[Any] = []
    faq: list[Any] = []
    gallery: list[Any] = []


# ─────────────────────────────────────────────────────────────────────
# Public profile schemas (/firmy listing + /firmy/{slug} profile page)
# ─────────────────────────────────────────────────────────────────────
# Shaped to never leak internal fields. The list endpoint returns
# `CompanyPublicSummary`; the detail endpoint returns `CompanyPublicDetail`.


class CompanyPublicSummary(BaseModel):
    """Card shown on /firmy. Designed for grid rendering — minimal payload."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str | None
    name: str
    is_verified: bool
    logo_url: str | None
    banner_url: str | None
    tagline: str | None
    industry: str | None
    employee_count: int | None
    hq_location: str | None
    founded_year: int | None
    remote_percentage: int | None
    tech_stack: list[Any]
    # Derived — joined from jobs at query time.
    open_jobs_count: int = 0


class CompanyPublicDetail(CompanyPublicSummary):
    """Full profile shown on /firmy/{slug}. Adds every JSONB section."""

    description: str | None
    website: str | None
    how_we_work: list[Any]
    benefits: list[Any]
    recruitment_process: list[Any]
    timeline: list[Any]
    faq: list[Any]
    gallery: list[Any]


class CompanyPublicListResponse(BaseModel):
    items: list[CompanyPublicSummary]
    total: int
