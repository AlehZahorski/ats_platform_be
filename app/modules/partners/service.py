"""Partner presentation helpers — token verification + deck loading."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.partners.models import PartnerAccessToken

# The deck is shipped alongside this module so it stays *out* of the public
# Next.js assets — it can only be reached after a token check.
_PRESENTATION_PATH = Path(__file__).with_name("presentation.html")

# mtime-keyed cache: we serve from memory but re-read whenever the file
# changes on disk. In dev the module dir is volume-mounted, so syncing a new
# deck (see scripts/sync-presentation.*) is picked up on the next request
# with no container restart. (cached_mtime, cached_html)
_cache: tuple[float, str] | None = None


def load_presentation_html() -> str:
    """Return the deck HTML, re-reading from disk only when it changed.

    Keyed on the file's modification time so an updated presentation.html is
    served immediately without a process restart, while unchanged files are
    served from memory.
    """
    global _cache
    try:
        mtime = _PRESENTATION_PATH.stat().st_mtime
    except FileNotFoundError:  # pragma: no cover - deployment guard
        return (
            "<!doctype html><meta charset='utf-8'>"
            "<p style='font-family:sans-serif;padding:2rem'>"
            "Prezentacja jest chwilowo niedostępna.</p>"
        )
    if _cache is None or _cache[0] != mtime:
        html = _PRESENTATION_PATH.read_text(encoding="utf-8")
        _cache = (mtime, html)
    return _cache[1]


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
    if row.max_views is not None and row.view_count >= row.max_views:
        return False
    return True
