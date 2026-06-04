from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class PartnerAccessToken(BaseModel):
    """A shareable access code that unlocks the investor presentation.

    Unlike auth refresh tokens (which we hash), this code is *meant* to be
    copied out of the admin UI and re-sent to a partner at any time, so we
    store it in plaintext. Threat model is low: it only gates a pitch deck,
    never personal or platform data.

    One token per investor/partner is the intended usage — `label` carries
    a human name ("Fundusz X / Jan Kowalski") so the admin can tell them
    apart, revoke individually, and see who actually opened the deck.
    """

    __tablename__ = "partner_access_tokens"

    # Human-readable owner of this token — shown in the admin list.
    label: Mapped[str] = mapped_column(Text, nullable=False)
    # Which deck this token unlocks: "investor" (pitch deck) or "partner"
    # (co-founder recruitment deck). The gate serves the matching HTML.
    deck: Mapped[str] = mapped_column(
        Text, nullable=False, default="investor", server_default="investor"
    )
    # The shareable secret the investor types on /prezentacja. Unique so a
    # lookup is unambiguous; indexed for the public verify hot path.
    token: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    # Optional free-form note for the admin (e.g. context, deal stage).
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Revocation switch — flip off to instantly kill access without deleting
    # the row (keeps the view history around).
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    # Optional hard expiry. NULL = never expires.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Optional cap on successful opens. NULL = unlimited.
    max_views: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Lightweight "who/when opened it" telemetry.
    view_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_viewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
