from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ─────────────────────────────────────────────────────────────────────
# Admin-side payloads
# ─────────────────────────────────────────────────────────────────────


class PartnerTokenCreate(BaseModel):
    """Mint a new access token. Only the label is required; the token
    string itself is generated server-side so it's always high-entropy."""

    label: str = Field(min_length=1, max_length=160)
    note: str | None = Field(default=None, max_length=2000)
    expires_at: datetime | None = None
    max_views: int | None = Field(default=None, ge=1, le=100000)


class PartnerTokenUpdate(BaseModel):
    """Partial update — revoke (is_active=false), rename, extend expiry, etc."""

    label: str | None = Field(default=None, min_length=1, max_length=160)
    note: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None
    expires_at: datetime | None = None
    max_views: int | None = Field(default=None, ge=1, le=100000)


class PartnerTokenRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str
    token: str
    note: str | None
    is_active: bool
    expires_at: datetime | None
    max_views: int | None
    view_count: int
    last_viewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PartnerTokenList(BaseModel):
    items: list[PartnerTokenRead]
    total: int


# ─────────────────────────────────────────────────────────────────────
# Public-side payloads
# ─────────────────────────────────────────────────────────────────────


class PresentationAccessRequest(BaseModel):
    token: str = Field(min_length=1, max_length=400)


class PresentationAccessResponse(BaseModel):
    """On success we return the full deck HTML so the FE can render it in a
    sandboxed iframe. Kept out of any GET so the code never lands in a URL
    that a proxy/log could capture."""

    html: str
