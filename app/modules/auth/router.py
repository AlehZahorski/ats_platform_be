import secrets
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentUser
from app.core.security import get_google_auth_url
from app.modules.auth.schemas import (
    LoginRequest,
    MessageResponse,
    SignupCompanyRequest,
)
from app.modules.auth.service import AuthService
from app.modules.users.schemas import UserRead

router = APIRouter()


def _get_auth_service(db: AsyncSession = Depends(get_db)) -> AuthService:
    return AuthService(db)


@router.post("/signup-company", response_model=MessageResponse, status_code=201)
async def signup_company(
    data: SignupCompanyRequest,
    background_tasks: BackgroundTasks,
    response: Response,
    service: AuthService = Depends(_get_auth_service),
) -> MessageResponse:
    result = await service.signup_company(data, background_tasks, response)
    return MessageResponse(**result)


@router.post("/login", response_model=MessageResponse)
async def login(
    request: Request,
    data: LoginRequest,
    response: Response,
    service: AuthService = Depends(_get_auth_service),
) -> MessageResponse:
    result = await service.login(data, response)
    return MessageResponse(**result)


@router.post("/refresh", response_model=MessageResponse)
async def refresh(
    response: Response,
    refresh_token: Optional[str] = Cookie(default=None),
    service: AuthService = Depends(_get_auth_service),
) -> MessageResponse:
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token")
    result = await service.refresh(refresh_token, response)
    return MessageResponse(**result)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    response: Response,
    refresh_token: Optional[str] = Cookie(default=None),
    service: AuthService = Depends(_get_auth_service),
) -> MessageResponse:
    result = await service.logout(refresh_token, response)
    return MessageResponse(**result)


@router.get("/me", response_model=UserRead)
async def me(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)


# ------------------------------------------------------------------
# Google OAuth
# ------------------------------------------------------------------
@router.get("/google")
async def google_login() -> dict:
    state = secrets.token_urlsafe(16)
    url = get_google_auth_url(state)
    return {"url": url, "state": state}


@router.get("/google/callback", response_model=MessageResponse)
async def google_callback(
    code: str,
    state: str,
    response: Response,
    service: AuthService = Depends(_get_auth_service),
) -> MessageResponse:
    result = await service.google_callback(code, response)
    return MessageResponse(**result)
