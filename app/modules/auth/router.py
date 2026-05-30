import secrets
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentUser
from app.core.exceptions import UnauthorizedError
from app.core.rate_limit import rate_limit
from app.core.i18n import t
from app.core.security import get_google_auth_url
from app.modules.auth.schemas import LoginRequest, MessageResponse, SignupCompanyRequest
from app.modules.auth.service import AuthService
from app.modules.companies.repository import CompanyRepository
from app.modules.users.repository import InvitationRepository, UserRepository
from app.modules.users.schemas import (
    AcceptInvitationRequest,
    InvitationPreview,
    UserRead,
)
from app.modules.users.service import InvitationService

router = APIRouter()


def _get_service(db: AsyncSession = Depends(get_db)) -> AuthService:
    return AuthService(UserRepository(db), CompanyRepository(db))


# audit_security C3: per-IP rate limit on the entire auth surface. Credential
# stuffing, account enumeration and refresh-token brute force are the three
# things this blocks. Keys default to per-user when authenticated; for the
# anonymous auth endpoints below the limiter falls back to per-IP.
@router.post(
    "/signup-company",
    response_model=MessageResponse,
    status_code=201,
    dependencies=[Depends(rate_limit("5/minute"))],
)
async def signup_company(
    data: SignupCompanyRequest,
    background_tasks: BackgroundTasks,
    response: Response,
    service: AuthService = Depends(_get_service),
) -> MessageResponse:
    result = await service.signup_company(data, background_tasks, response)
    return MessageResponse(**result)


@router.post(
    "/login",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit("5/minute"))],
)
async def login(
    data: LoginRequest,
    response: Response,
    service: AuthService = Depends(_get_service),
) -> MessageResponse:
    result = await service.login(data, response)
    return MessageResponse(**result)


@router.post(
    "/refresh",
    response_model=MessageResponse,
    # Slightly more permissive — clients refresh on app start and on 401.
    dependencies=[Depends(rate_limit("30/minute"))],
)
async def refresh(
    response: Response,
    refresh_token: Optional[str] = Cookie(default=None),
    service: AuthService = Depends(_get_service),
) -> MessageResponse:
    if not refresh_token:
        raise UnauthorizedError(t("auth.no_refresh_token"))
    result = await service.refresh(refresh_token, response)
    return MessageResponse(**result)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    response: Response,
    refresh_token: Optional[str] = Cookie(default=None),
    service: AuthService = Depends(_get_service),
) -> MessageResponse:
    result = await service.logout(refresh_token, response)
    return MessageResponse(**result)


@router.get("/me", response_model=UserRead)
async def me(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)


@router.get("/google")
async def google_login() -> dict:
    state = secrets.token_urlsafe(16)
    return {"url": get_google_auth_url(state), "state": state}


# audit_security C3: OAuth callback is publicly callable and the only barrier
# against replay/abuse is the (still-incomplete) state validation. Cap it.
@router.get(
    "/google/callback",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit("10/minute"))],
)
async def google_callback(
    code: str,
    state: str,
    response: Response,
    service: AuthService = Depends(_get_service),
) -> MessageResponse:
    result = await service.google_callback(code, response)
    return MessageResponse(**result)


# ---------------------------------------------------------------------------
# Invitation flow — public (no auth)
# ---------------------------------------------------------------------------
def _invitation_service(db: AsyncSession = Depends(get_db)) -> InvitationService:
    return InvitationService(
        InvitationRepository(db),
        UserRepository(db),
        CompanyRepository(db),
    )


# F-M6 / F-M8 (audit_api): per-IP rate-limit to slow brute-force of invitation
# tokens + ``Cache-Control: no-store`` so the (sensitive) preview payload
# never lands in a shared proxy cache.
@router.get(
    "/invitation/{token}",
    response_model=InvitationPreview,
    dependencies=[Depends(rate_limit("10/minute"))],
)
async def preview_invitation(
    token: str,
    response: Response,
    service: InvitationService = Depends(_invitation_service),
) -> InvitationPreview:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    invitation, company_name = await service.preview(token)
    return InvitationPreview(
        email=invitation.email,
        role=invitation.role,
        company_name=company_name,
        expires_at=invitation.expires_at,
    )


@router.post("/accept-invitation", response_model=UserRead)
async def accept_invitation(
    data: AcceptInvitationRequest,
    response: Response,
    service: InvitationService = Depends(_invitation_service),
) -> UserRead:
    user = await service.accept(raw_token=data.token, password=data.password, response=response)
    return UserRead.model_validate(user)
