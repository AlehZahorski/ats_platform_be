from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ─────────────────────────────────────────────────────────────────────
# Public read shapes
# ─────────────────────────────────────────────────────────────────────

class ArticleAuthor(BaseModel):
    """Embedded in every article response so the card UI can render
    name + role + avatar without a second round-trip."""
    name:       str
    role:       str | None = None
    avatar_url: str | None = None


class ArticleBrandCompany(BaseModel):
    """Slim company block, only present on type='company' articles.
    Lets the FE render the "@ Brainly" tail of the byline + clickable
    chip linking to /firmy/{slug} without re-fetching the full company."""
    id:           uuid.UUID
    slug:         str | None
    name:         str
    logo_url:     str | None
    is_verified:  bool


class ArticleSummary(BaseModel):
    """Slim shape for the grid + featured slot — works for both
    editorial (/poradnik) and company (/firmy-pisza) lists."""
    model_config = ConfigDict(from_attributes=True)

    id:                uuid.UUID
    slug:              str
    title:             str
    excerpt:           str | None
    cover_image_url:   str | None
    category:          str
    is_featured:       bool
    # Promotion flag — only meaningful for type='company' rows surfaced on
    # the editorial /poradnik feed. UI renders a "Promowane" chip.
    is_promoted:       bool = False
    promoted_until:    datetime | None = None
    type:              str
    company:           ArticleBrandCompany | None = None
    author:            ArticleAuthor
    read_time_minutes: int | None
    published_at:      datetime | None


class ArticleDetail(ArticleSummary):
    """Full article — adds the HTML body. Used by /poradnik/{slug}."""
    content: str


class ArticleList(BaseModel):
    items: list[ArticleSummary]
    total: int


class CategoryCount(BaseModel):
    category: str
    count:    int


# ─────────────────────────────────────────────────────────────────────
# Newsletter
# ─────────────────────────────────────────────────────────────────────

class NewsletterSubscribeRequest(BaseModel):
    email:  EmailStr
    # Free-form attribution. The FE sends "poradnik" for now; we store
    # whatever shows up so a future homepage widget can use the same endpoint.
    source: str | None = Field(default=None, max_length=80)


class NewsletterSubscribeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    email:           EmailStr
    subscribed_at:   datetime
    already_existed: bool


# ─────────────────────────────────────────────────────────────────────
# Admin-side payloads
# ─────────────────────────────────────────────────────────────────────

class ArticleCreate(BaseModel):
    """Create payload for /admin/articles. Slug + author are required
    so the row is never half-baked; everything else can be filled in
    later, including the cover image (uploaded after create)."""
    slug:              str = Field(min_length=3, max_length=120)
    title:             str = Field(min_length=1, max_length=240)
    excerpt:           str | None = Field(default=None, max_length=400)
    content:           str = Field(default="", description="HTML body. Empty allowed for a fresh draft.")
    category:          str = Field(min_length=1, max_length=40)
    is_featured:       bool = False
    is_published:      bool = False
    author_name:       str = Field(min_length=1, max_length=120)
    author_role:       str | None = Field(default=None, max_length=120)
    author_avatar_url: str | None = None
    read_time_minutes: int | None = Field(default=None, ge=1, le=120)
    published_at:      datetime | None = None


class ArticleUpdate(BaseModel):
    """Partial update — every field is optional so the editor can save
    one section at a time."""
    slug:              str | None = Field(default=None, min_length=3, max_length=120)
    title:             str | None = Field(default=None, min_length=1, max_length=240)
    excerpt:           str | None = Field(default=None, max_length=400)
    content:           str | None = None
    category:          str | None = Field(default=None, min_length=1, max_length=40)
    is_featured:       bool | None = None
    is_published:      bool | None = None
    author_name:       str | None = Field(default=None, min_length=1, max_length=120)
    author_role:       str | None = Field(default=None, max_length=120)
    author_avatar_url: str | None = None
    read_time_minutes: int | None = Field(default=None, ge=1, le=120)
    published_at:      datetime | None = None


class ArticleAdminRead(ArticleDetail):
    """Admin view — extends the public detail with the publish flag
    (public version filters drafts out at the query level)."""
    is_published: bool
    created_at:   datetime
    updated_at:   datetime


class ArticleAdminList(BaseModel):
    items: list[ArticleAdminRead]
    total: int
