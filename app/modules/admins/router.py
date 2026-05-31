"""Admin auth router — login / logout / refresh / me.

All endpoints live under /api/v1/admin/auth and set/clear the
`admin_access_token` + `admin_refresh_token` cookies. No cross-mixing
with /candidates/auth — different identity, different cookies.
"""

from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.modules.admins.dependencies import CurrentAdmin
from app.modules.admins.repository import AdminRepository
from app.modules.admins.schemas import AdminLoginRequest, AdminRead
from app.modules.admins.service import (
    ADMIN_REFRESH_COOKIE,
    AdminAuthService,
)

router = APIRouter()


def _auth(db: AsyncSession = Depends(get_db)) -> AdminAuthService:
    return AdminAuthService(AdminRepository(db))


# audit_security C3: admin login surface is the most sensitive — keep it the
# tightest. 3/minute lets a legitimate operator recover from a typo but stops
# any automated stuffing within seconds.
@router.post(
    "/login",
    response_model=AdminRead,
    dependencies=[Depends(rate_limit("3/minute"))],
)
async def login(
    data: AdminLoginRequest,
    response: Response,
    service: AdminAuthService = Depends(_auth),
) -> AdminRead:
    admin = await service.login(email=data.email, password=data.password, response=response)
    return AdminRead.model_validate(admin)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    admin_refresh_token: str | None = Cookie(default=None, alias=ADMIN_REFRESH_COOKIE),
    service: AdminAuthService = Depends(_auth),
) -> Response:
    await service.logout(refresh_token=admin_refresh_token, response=response)
    return Response(status_code=204)


@router.post(
    "/refresh",
    response_model=AdminRead,
    dependencies=[Depends(rate_limit("30/minute"))],
)
async def refresh(
    response: Response,
    admin_refresh_token: str | None = Cookie(default=None, alias=ADMIN_REFRESH_COOKIE),
    service: AdminAuthService = Depends(_auth),
) -> AdminRead:
    # Refresh requires the cookie — if absent, force a fresh login.
    from app.core.exceptions import UnauthorizedError

    if not admin_refresh_token:
        raise UnauthorizedError("Sesja wygasła, zaloguj się ponownie")
    admin = await service.refresh(refresh_token=admin_refresh_token, response=response)
    return AdminRead.model_validate(admin)


@router.get("/me", response_model=AdminRead)
async def me(admin: CurrentAdmin) -> AdminRead:
    return AdminRead.model_validate(admin)
