import uuid
from typing import Annotated, Any, Optional

from fastapi import Cookie, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_access_token

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
DbSession = Annotated[AsyncSession, Depends(get_db)]


# ---------------------------------------------------------------------------
# Current user dependency
# ---------------------------------------------------------------------------
async def get_current_user(
    db: DbSession,
    access_token: Optional[str] = Cookie(default=None),
) -> Any:
    from app.modules.users.models import User

    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not access_token:
        raise credentials_exc

    try:
        payload = decode_access_token(access_token)
        user_id: str = payload.get("sub", "")
        if not user_id:
            raise credentials_exc
    except JWTError:
        raise credentials_exc

    result = await db.execute(
        select(User).where(User.id == uuid.UUID(user_id))
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exc

    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email address not verified",
        )

    return user


# ---------------------------------------------------------------------------
# Current company dependency
# ---------------------------------------------------------------------------
async def get_current_company(
    current_user: Any = Depends(get_current_user),
    db: DbSession = None,
) -> Any:
    from app.modules.companies.models import Company

    result = await db.execute(
        select(Company).where(Company.id == current_user.company_id)
    )
    company = result.scalar_one_or_none()

    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found",
        )

    return company


# ---------------------------------------------------------------------------
# Role guard factory
# ---------------------------------------------------------------------------
def require_roles(*roles: str):
    async def _check(
        current_user: Any = Depends(get_current_user),
    ) -> Any:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role}' is not permitted for this action",
            )
        return current_user
    return _check


# ---------------------------------------------------------------------------
# Annotated shorthand types for router injection
# ---------------------------------------------------------------------------
CurrentUser = Annotated[Any, Depends(get_current_user)]
CurrentCompany = Annotated[Any, Depends(get_current_company)]