"""Auth dependency for admin-side endpoints.

Parses the `admin_access_token` cookie and loads the matching Admin
row. Raises 401 if missing/invalid. Mirrors the candidate dependency
shape so call sites are symmetric across identity types.
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
from app.modules.admins.models import Admin
from app.modules.admins.service import ADMIN_ACCESS_COOKIE


async def get_current_admin(
    db: AsyncSession = Depends(get_db),
    admin_access_token: str | None = Cookie(default=None, alias=ADMIN_ACCESS_COOKIE),
) -> Admin:
    creds_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Wymagane logowanie administratora",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not admin_access_token:
        raise creds_exc
    try:
        # audit_security H: explicit expected_type so an HR access token
        # signed with the same secret cannot satisfy this dependency. The
        # belt-and-suspenders `payload.get("type")` check is now redundant
        # but kept until a follow-up sprint cleans both call sites.
        payload = decode_access_token(admin_access_token, expected_type="admin")
        if payload.get("type") != "admin":
            raise creds_exc
        admin_id = payload.get("admin_id") or payload.get("sub")
        if not admin_id:
            raise creds_exc
    except JWTError:
        raise creds_exc

    result = await db.execute(select(Admin).where(Admin.id == uuid.UUID(admin_id)))
    admin = result.scalar_one_or_none()
    if admin is None or not admin.is_active:
        raise creds_exc
    return admin


CurrentAdmin = Annotated[Admin, Depends(get_current_admin)]
