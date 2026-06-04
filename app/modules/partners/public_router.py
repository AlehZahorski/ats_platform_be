"""Public presentation gate. No admin auth — access is the token itself.

Flow: investor opens /prezentacja, types the code the admin sent them, the
FE POSTs it here. We verify (active / not expired / under view cap), bump
the view counter, and return the deck HTML. Rate-limited per IP so the
token space can't be brute-forced.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.modules.partners.schemas import (
    PresentationAccessRequest,
    PresentationAccessResponse,
)
from app.modules.partners.service import (
    get_token_row,
    load_presentation_html,
    token_is_valid,
)

router = APIRouter()


@router.post(
    "/access",
    response_model=PresentationAccessResponse,
    dependencies=[Depends(rate_limit("10/minute"))],
)
async def access_presentation(
    data: PresentationAccessRequest,
    db: AsyncSession = Depends(get_db),
) -> PresentationAccessResponse:
    # One opaque error for every failure mode (unknown / revoked / expired /
    # exhausted) so a prober can't tell a wrong code from a disabled one.
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Nieprawidłowy lub nieaktywny kod dostępu.",
    )

    row = await get_token_row(db, data.token)
    if row is None or not token_is_valid(row):
        raise invalid

    # Count the successful open. Done in the same transaction so a view cap
    # can't be raced past by parallel requests beyond the commit boundary.
    row.view_count += 1
    row.last_viewed_at = datetime.now(UTC)
    await db.commit()

    return PresentationAccessResponse(html=load_presentation_html())
