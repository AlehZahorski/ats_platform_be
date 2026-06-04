"""Admin CRUD for partner/investor access tokens.

Behind CurrentAdmin and mounted at /admin/partners. Drives the "Partnerzy"
tab: mint a token per investor, copy the share link, revoke, and see who
opened the deck.
"""

from __future__ import annotations

import secrets
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import NotFoundError
from app.modules.admins.dependencies import CurrentAdmin
from app.modules.partners.models import PartnerAccessToken
from app.modules.partners.schemas import (
    PartnerTokenCreate,
    PartnerTokenList,
    PartnerTokenRead,
    PartnerTokenUpdate,
)

router = APIRouter()


def _generate_code() -> str:
    """Short, URL-safe, human-shareable access code (~26 chars of entropy)."""
    return secrets.token_urlsafe(18)


@router.get("", response_model=PartnerTokenList)
async def list_tokens(
    _admin: CurrentAdmin,
    q: str | None = Query(None, min_length=1),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    base = select(PartnerAccessToken)
    if q:
        term = f"%{q.strip()}%"
        base = base.where(
            PartnerAccessToken.label.ilike(term) | PartnerAccessToken.note.ilike(term)
        )
    base = base.order_by(PartnerAccessToken.created_at.desc())

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.execute(base.offset(skip).limit(limit))).scalars().all()
    return {"items": list(rows), "total": total}


@router.post("", response_model=PartnerTokenRead, status_code=status.HTTP_201_CREATED)
async def create_token(
    data: PartnerTokenCreate,
    _admin: CurrentAdmin,
    db: AsyncSession = Depends(get_db),
) -> PartnerAccessToken:
    # Collision is astronomically unlikely, but the column is unique — retry
    # a couple of times rather than 500 on the off chance.
    for _ in range(5):
        code = _generate_code()
        exists = (
            await db.execute(
                select(PartnerAccessToken.id).where(PartnerAccessToken.token == code)
            )
        ).scalar_one_or_none()
        if exists is None:
            break
    row = PartnerAccessToken(
        label=data.label,
        deck=data.deck,
        token=code,
        note=data.note,
        expires_at=data.expires_at,
        max_views=data.max_views,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.patch("/{token_id}", response_model=PartnerTokenRead)
async def update_token(
    token_id: uuid.UUID,
    data: PartnerTokenUpdate,
    _admin: CurrentAdmin,
    db: AsyncSession = Depends(get_db),
) -> PartnerAccessToken:
    row = await _require(db, token_id)
    payload = data.model_dump(exclude_unset=True)
    for field, value in payload.items():
        setattr(row, field, value)
    await db.commit()
    await db.refresh(row)
    return row


@router.post("/{token_id}/regenerate", response_model=PartnerTokenRead)
async def regenerate_token(
    token_id: uuid.UUID,
    _admin: CurrentAdmin,
    db: AsyncSession = Depends(get_db),
) -> PartnerAccessToken:
    """Roll the code (e.g. if a link leaked) and reset its view counter."""
    row = await _require(db, token_id)
    for _ in range(5):
        code = _generate_code()
        exists = (
            await db.execute(
                select(PartnerAccessToken.id).where(PartnerAccessToken.token == code)
            )
        ).scalar_one_or_none()
        if exists is None:
            break
    row.token = code
    row.view_count = 0
    row.last_viewed_at = None
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_token(
    token_id: uuid.UUID,
    _admin: CurrentAdmin,
    db: AsyncSession = Depends(get_db),
) -> Response:
    row = await _require(db, token_id)
    await db.delete(row)
    await db.commit()
    return Response(status_code=204)


async def _require(db: AsyncSession, token_id: uuid.UUID) -> PartnerAccessToken:
    row = (
        await db.execute(
            select(PartnerAccessToken).where(PartnerAccessToken.id == token_id)
        )
    ).scalar_one_or_none()
    if not row:
        raise NotFoundError("Token nie został znaleziony.")
    return row
