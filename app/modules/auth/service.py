from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)

from fastapi import BackgroundTasks, Response

from app.core.base_service import BaseService
from app.core.config import settings
from app.core.enums.users import UserRole
from app.core.exceptions import ConflictError, ForbiddenError, UnauthorizedError, UnprocessableError
from app.core.i18n import t
from app.core.security import (
    access_token_cookie_max_age,
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
from app.modules.users.repository import UserRepository
from app.services.mailer import mail_service


class AuthService(BaseService[UserRepository]):
    def __init__(self, repository: UserRepository, company_repo: CompanyRepository) -> None:
        super().__init__(repository)
        self.company_repo = company_repo

    # ------------------------------------------------------------------
    # Signup
    # ------------------------------------------------------------------
    async def signup_company(
        self,
        data: SignupCompanyRequest,
        background_tasks: BackgroundTasks,
        response: Response,
    ) -> dict:
        if await self.repository.get_by_email(data.email):
            raise ConflictError(t("auth.email_already_registered"))

        company = await self.company_repo.create(CompanyCreate(name=data.company_name))
        user = await self.repository.create(
            company_id=company.id,
            email=data.email,
            password_hash=hash_password(data.password),
            role=UserRole.owner,
            is_verified=settings.app_env == "development",
        )

        try:
            token = secrets.token_urlsafe(32)
            verification_url = (
                f"{settings.frontend_url}/verify-email?token={token}&user_id={user.id}"
            )
            mail_service.send_verification_email(background_tasks, user.email, verification_url)
        except Exception:
            # H4 (audit_backend_code): swallow the email failure so signup still
            # succeeds (user can request a re-send), but at least log it — the
            # silent `pass` made bounce/SMTP-down incidents invisible in prod.
            logger.exception("Failed to enqueue verification email for %s", user.email)

        msg = (
            t("auth.company_created")
            if settings.app_env == "development"
            else t("auth.company_created_verify")
        )
        return {"message": msg}

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------
    # audit_security L: pre-computed once at startup — a real bcrypt hash so
    # `verify_password` against it costs the same as a real check. Used to
    # equalise response time when the email does not exist.
    _DUMMY_BCRYPT_HASH = "$2b$12$c5XSPYwbVbhEahCqUe3lA.ZDjzn3xn93rGmm4eJG1OQTehVDH8H/q"

    async def login(self, data: LoginRequest, response: Response) -> dict:
        user = await self.repository.get_by_email(data.email)
        if not user:
            # Run a dummy bcrypt verify so the response time matches the
            # "user exists, wrong password" path within a few ms — prevents
            # account enumeration by timing.
            verify_password(data.password, self._DUMMY_BCRYPT_HASH)
            raise UnauthorizedError(t("auth.invalid_credentials"))
        if not verify_password(data.password, user.password_hash):
            raise UnauthorizedError(t("auth.invalid_credentials"))
        if not user.is_verified:
            raise ForbiddenError(t("auth.email_not_verified"))

        access_token = create_access_token(
            subject=str(user.id),
            extra_claims={"company_id": str(user.company_id), "role": user.role},
        )
        raw_refresh, token_hash = create_refresh_token()
        expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
        await self.repository.save_refresh_token(user.id, token_hash, expires_at)

        self._set_auth_cookies(response, access_token, raw_refresh)
        return {"message": t("auth.logged_in")}

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------
    async def refresh(self, raw_token: str, response: Response) -> dict:
        stored = await self.repository.get_refresh_token(hash_token(raw_token))
        if not stored:
            raise UnauthorizedError(t("auth.invalid_refresh_token"))

        user = await self.repository.get_by_id(stored.user_id)
        if not user:
            raise UnauthorizedError(t("auth.user_not_found"))

        await self.repository.revoke_refresh_token(stored)
        raw_new, new_hash = create_refresh_token()
        expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
        await self.repository.save_refresh_token(user.id, new_hash, expires_at)

        access_token = create_access_token(
            subject=str(user.id),
            extra_claims={"company_id": str(user.company_id), "role": user.role},
        )
        self._set_auth_cookies(response, access_token, raw_new)
        return {"message": t("auth.token_refreshed")}

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------
    async def logout(self, raw_token: str | None, response: Response) -> dict:
        if raw_token:
            stored = await self.repository.get_refresh_token(hash_token(raw_token))
            if stored:
                await self.repository.revoke_refresh_token(stored)
        self._clear_auth_cookies(response)
        return {"message": t("auth.logged_out")}

    # ------------------------------------------------------------------
    # Google OAuth
    # ------------------------------------------------------------------
    async def google_callback(self, code: str, response: Response) -> dict:
        google_user = await exchange_google_code(code)
        email = google_user.get("email")
        if not email:
            raise UnprocessableError(t("auth.google_email_missing"))

        user = await self.repository.get_by_email(email)
        if not user:
            company = await self.company_repo.create(
                CompanyCreate(name=google_user.get("name", email.split("@")[0]))
            )
            user = await self.repository.create(
                company_id=company.id,
                email=email,
                password_hash=hash_password(secrets.token_hex(32)),
                role=UserRole.owner,
                is_verified=True,
            )

        access_token = create_access_token(
            subject=str(user.id),
            extra_claims={"company_id": str(user.company_id), "role": user.role},
        )
        raw_refresh, token_hash = create_refresh_token()
        expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
        await self.repository.save_refresh_token(user.id, token_hash, expires_at)
        self._set_auth_cookies(response, access_token, raw_refresh)
        return {"message": t("auth.logged_in_google")}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
        secure = settings.is_production
        response.set_cookie(
            "access_token",
            access_token,
            httponly=True,
            secure=secure,
            samesite="lax",
            max_age=access_token_cookie_max_age(),
        )
        response.set_cookie(
            "refresh_token",
            refresh_token,
            httponly=True,
            secure=secure,
            samesite="lax",
            max_age=settings.refresh_token_expire_days * 86400,
            path="/api/v1/auth/refresh",
        )

    @staticmethod
    def _clear_auth_cookies(response: Response) -> None:
        response.delete_cookie("access_token")
        response.delete_cookie("refresh_token", path="/api/v1/auth/refresh")
