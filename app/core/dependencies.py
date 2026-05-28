import uuid
from typing import TYPE_CHECKING, Annotated, Optional

from fastapi import Cookie, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.i18n import t
from app.core.security import decode_access_token

# L5 (audit_backend_code): type the dependency returns properly so every
# route handler gets working autocompletion and pyright/mypy checks. The
# imports are deferred to TYPE_CHECKING so we keep the runtime side free of
# the existing circular-import hazard (the models import this module).
if TYPE_CHECKING:
    from app.modules.companies.models import Company
    from app.modules.users.models import User

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
) -> "User":
    from app.modules.users.models import User

    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=t("auth.credentials_invalid"),
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not access_token:
        raise credentials_exc

    # M3 (audit_backend_code): also catch ValueError so a malformed `sub`
    # claim (e.g. not a UUID) returns 401 instead of bubbling up to the
    # global 500 handler.
    try:
        payload = decode_access_token(access_token)
        user_id: str = payload.get("sub", "")
        if not user_id:
            raise credentials_exc
        user_uuid = uuid.UUID(user_id)
    except (JWTError, ValueError):
        raise credentials_exc

    result = await db.execute(
        select(User).where(User.id == user_uuid)
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exc

    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=t("auth.email_not_verified_dep"),
        )

    if not getattr(user, "is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=t("auth.account_deactivated"),
        )

    return user


# ---------------------------------------------------------------------------
# Current company dependency
# ---------------------------------------------------------------------------
# H3 (audit_backend_code): `db` no longer has a falsy default. The previous
# `DbSession = None` only worked because FastAPI's Depends-resolver fills it
# in regardless — any direct call would have NPE'd on the first
# `db.execute`. Order: non-default param first.
async def get_current_company(
    db: DbSession,
    current_user: "User" = Depends(get_current_user),
) -> "Company":
    from app.modules.companies.models import Company

    result = await db.execute(
        select(Company).where(Company.id == current_user.company_id)
    )
    company = result.scalar_one_or_none()

    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=t("auth.company_not_found"),
        )

    return company


# ---------------------------------------------------------------------------
# Role guard factory
# ---------------------------------------------------------------------------
def require_roles(*roles: str):
    async def _check(
        current_user: "User" = Depends(get_current_user),
    ) -> "User":
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=t("auth.role_not_permitted", role=current_user.role),
            )
        return current_user
    return _check


# ---------------------------------------------------------------------------
# Annotated shorthand types for router injection
# ---------------------------------------------------------------------------
# L5 (audit_backend_code): strings so the forward refs resolve lazily and we
# don't break the import order while still giving IDE / type-checker the
# correct model type.
CurrentUser = Annotated["User", Depends(get_current_user)]
CurrentCompany = Annotated["Company", Depends(get_current_company)]
RecruiterOrOwner = Annotated["User", Depends(require_roles("owner", "recruiter"))]
OwnerOnly = Annotated["User", Depends(require_roles("owner"))]
