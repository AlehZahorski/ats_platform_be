from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from fastapi import BackgroundTasks, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    exchange_google_code,
    hash_password,
    hash_token,
    verify_password,
)
from app.modules.auth.schemas import LoginRequest, SignupCompanyRequest
from app.modules.companies.repository import CompanyRepository
from app.modules.companies.schemas import CompanyCreate
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from app.services.mailer import mail_service


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    # With Next.js proxy, frontend and backend share the same origin
    # so SameSite=lax works fine and Secure=False is OK for http dev
    samesite = "lax"
    secure = settings.is_production

    response.set_cookie(
        "access_token",
        access_token,
        httponly=True,
        secure=secure,
        samesite=samesite,
        max_age=settings.access_token_expire_minutes * 60,
    )
    response.set_cookie(
        "refresh_token",
        refresh_token,
        httponly=True,
        secure=secure,
        samesite=samesite,
        max_age=settings.refresh_token_expire_days * 86400,
        path="/api/v1/auth/refresh",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token", path="/api/v1/auth/refresh")


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.user_repo = UserRepository(db)
        self.company_repo = CompanyRepository(db)

    # ------------------------------------------------------------------
    # Signup
    # ------------------------------------------------------------------
    async def signup_company(
        self,
        data: SignupCompanyRequest,
        background_tasks: BackgroundTasks,
        response: Response,
    ) -> dict:
        existing = await self.user_repo.get_by_email(data.email)
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

        company = await self.company_repo.create(CompanyCreate(name=data.company_name))
        user = await self.user_repo.create(
            company_id=company.id,
            email=data.email,
            password_hash=hash_password(data.password),
            role="owner",
            # Auto-verify in development so you can log in immediately
            is_verified=settings.app_env == "development",
        )

        # Send verification email (best-effort — won't crash if SMTP not configured)
        try:
            token = secrets.token_urlsafe(32)
            verification_url = f"{settings.frontend_url}/verify-email?token={token}&user_id={user.id}"
            mail_service.send_verification_email(background_tasks, user.email, verification_url)
        except Exception:
            pass  # SMTP not configured in dev — that's fine

        msg = "Company created." if settings.app_env == "development" else "Company created. Please verify your email address."
        return {"message": msg}

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------
    async def login(
        self,
        data: LoginRequest,
        response: Response,
    ) -> dict:
        user = await self.user_repo.get_by_email(data.email)
        if not user or not verify_password(data.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )
        if not user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email not verified",
            )

        access_token = create_access_token(
            subject=str(user.id),
            extra_claims={"company_id": str(user.company_id), "role": user.role},
        )
        raw_refresh, token_hash = create_refresh_token()
        expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
        await self.user_repo.save_refresh_token(user.id, token_hash, expires_at)

        _set_auth_cookies(response, access_token, raw_refresh)
        return {"message": "Logged in successfully"}

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------
    async def refresh(self, raw_token: str, response: Response) -> dict:
        token_hash = hash_token(raw_token)
        stored = await self.user_repo.get_refresh_token(token_hash)
        if not stored:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

        user = await self.user_repo.get_by_id(stored.user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

        # Rotate refresh token
        await self.user_repo.revoke_refresh_token(stored)
        raw_new, new_hash = create_refresh_token()
        expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
        await self.user_repo.save_refresh_token(user.id, new_hash, expires_at)

        access_token = create_access_token(
            subject=str(user.id),
            extra_claims={"company_id": str(user.company_id), "role": user.role},
        )
        _set_auth_cookies(response, access_token, raw_new)
        return {"message": "Token refreshed"}

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------
    async def logout(self, raw_token: str | None, response: Response) -> dict:
        if raw_token:
            token_hash = hash_token(raw_token)
            stored = await self.user_repo.get_refresh_token(token_hash)
            if stored:
                await self.user_repo.revoke_refresh_token(stored)
        _clear_auth_cookies(response)
        return {"message": "Logged out"}

    # ------------------------------------------------------------------
    # Google OAuth
    # ------------------------------------------------------------------
    async def google_callback(
        self,
        code: str,
        response: Response,
    ) -> dict:
        google_user = await exchange_google_code(code)
        email = google_user.get("email")
        if not email:
            raise HTTPException(status_code=400, detail="Could not retrieve email from Google")

        user = await self.user_repo.get_by_email(email)
        if not user:
            # Auto-create a personal company for OAuth signups
            company = await self.company_repo.create(
                CompanyCreate(name=google_user.get("name", email.split("@")[0]))
            )
            user = await self.user_repo.create(
                company_id=company.id,
                email=email,
                password_hash=hash_password(secrets.token_hex(32)),  # unusable password
                role="owner",
                is_verified=True,
            )

        access_token = create_access_token(
            subject=str(user.id),
            extra_claims={"company_id": str(user.company_id), "role": user.role},
        )
        raw_refresh, token_hash = create_refresh_token()
        expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
        await self.user_repo.save_refresh_token(user.id, token_hash, expires_at)
        _set_auth_cookies(response, access_token, raw_refresh)
        return {"message": "Logged in with Google"}