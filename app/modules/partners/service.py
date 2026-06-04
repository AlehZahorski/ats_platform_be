"""Partner presentation helpers — token verification + deck loading."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.partners.models import PartnerAccessToken

# Decks are shipped alongside this module so they stay *out* of the public
# Next.js assets — reachable only after a token check. One file per audience.
_DECK_FILES = {
    "investor": Path(__file__).with_name("presentation.html"),
    "partner": Path(__file__).with_name("presentation-partner.html"),
}

# mtime-keyed cache per deck: serve from memory but re-read whenever the file
# changes on disk. In dev the module dir is volume-mounted, so syncing a new
# deck (see scripts/sync-presentation.*) is picked up on the next request with
# no container restart. {deck: (cached_mtime, cached_html)}
_cache: dict[str, tuple[float, str]] = {}


def load_presentation_html(deck: str = "investor") -> str:
    """Return the deck HTML for the given audience, re-reading only on change.

    `deck` is "investor" or "partner". Falls back to the investor deck for any
    unknown value so a bad DB row can never 500 the gate.
    """
    path = _DECK_FILES.get(deck, _DECK_FILES["investor"])
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:  # pragma: no cover - deployment guard
        return (
            "<!doctype html><meta charset='utf-8'>"
            "<p style='font-family:sans-serif;padding:2rem'>"
            "Prezentacja jest chwilowo niedostępna.</p>"
        )
    cached = _cache.get(deck)
    if cached is None or cached[0] != mtime:
        html = path.read_text(encoding="utf-8")
        _cache[deck] = (mtime, html)
        return html
    return cached[1]


async def get_token_row(db: AsyncSession, token: str) -> PartnerAccessToken | None:
    token = (token or "").strip()
    if not token:
        return None
    result = await db.execute(
        select(PartnerAccessToken).where(PartnerAccessToken.token == token)
    )
    return result.scalar_one_or_none()


def token_is_valid(row: PartnerAccessToken, *, now: datetime | None = None) -> bool:
    """Active, not expired, and under the optional view cap."""
    now = now or datetime.now(UTC)
    if not row.is_active:
        return False
    if row.expires_at is not None and row.expires_at <= now:
        return False
    return not (row.max_views is not None and row.view_count >= row.max_views)
