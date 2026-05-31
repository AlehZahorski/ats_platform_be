"""Auth dependency for candidate-side endpoints.

Parses the `candidate_access_token` cookie (separate from the recruiter
`access_token` cookie) and loads the matching Candidate row. Raises 401
if missing/invalid.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_access_token
from app.modules.candidates.models import Candidate
from app.modules.candidates.service import CANDIDATE_ACCESS_COOKIE


async def get_current_candidate(
    db: AsyncSession = Depends(get_db),
    candidate_access_token: str | None = Cookie(default=None, alias=CANDIDATE_ACCESS_COOKIE),
) -> Candidate:
    creds_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Wymagane logowanie",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not candidate_access_token:
        raise creds_exc
    try:
        # audit_security H: lock token type at the JWT-validation step.
        payload = decode_access_token(candidate_access_token, expected_type="candidate")
        if payload.get("type") != "candidate":
            raise creds_exc
        candidate_id = payload.get("candidate_id") or payload.get("sub")
        if not candidate_id:
            raise creds_exc
    except JWTError:
        raise creds_exc

    result = await db.execute(select(Candidate).where(Candidate.id == uuid.UUID(candidate_id)))
    candidate = result.scalar_one_or_none()
    if candidate is None or not candidate.is_active:
        raise creds_exc
    return candidate


async def get_optional_candidate(
    db: AsyncSession = Depends(get_db),
    candidate_access_token: str | None = Cookie(default=None, alias=CANDIDATE_ACCESS_COOKIE),
) -> Candidate | None:
    """Same as `get_current_candidate` but returns None instead of raising 401.
    Used by endpoints that work both logged-in (e.g. attribute search-log entries)
    and anonymously."""
    if not candidate_access_token:
        return None
    try:
        payload = decode_access_token(candidate_access_token, expected_type="candidate")
        if payload.get("type") != "candidate":
            return None
        candidate_id = payload.get("candidate_id") or payload.get("sub")
        if not candidate_id:
            return None
    except JWTError:
        return None
    result = await db.execute(select(Candidate).where(Candidate.id == uuid.UUID(candidate_id)))
    candidate = result.scalar_one_or_none()
    return candidate if (candidate and candidate.is_active) else None


CurrentCandidate = Annotated[Candidate, Depends(get_current_candidate)]
OptionalCandidate = Annotated[Candidate | None, Depends(get_optional_candidate)]
