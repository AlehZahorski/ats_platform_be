from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import Response

from app.core.config import settings
from app.core.exceptions import UnauthorizedError
from app.core.security import (
    access_token_cookie_max_age,
    create_access_token,
    create_refresh_token,
    hash_token,
    verify_password,
)
from app.modules.admins.models import Admin
from app.modules.admins.repository import AdminRepository

# Distinct cookie names — admins coexist with recruiter (`access_token`)
# and candidate (`candidate_access_token`) sessions in the same browser.
ADMIN_ACCESS_COOKIE = "admin_access_token"
ADMIN_REFRESH_COOKIE = "admin_refresh_token"
ADMIN_REFRESH_COOKIE_PATH = "/api/v1/admin/auth/refresh"


class AdminAuthService:
    def __init__(self, repo: AdminRepository) -> None:
        self.repo = repo

    async def login(self, *, email: str, password: str, response: Response) -> Admin:
        admin = await self.repo.get_by_email(email.strip().lower())
        if not admin or not verify_password(password, admin.password_hash):
            # Same generic message regardless of which side failed — gives no
            # signal to attackers about whether the email exists.
            raise UnauthorizedError("Nieprawidłowy e-mail lub hasło")
        if not admin.is_active:
            raise UnauthorizedError("Konto zostało zdezaktywowane")
        await self.repo.touch_last_login(admin)
        await self._issue_session(admin, response)
        return admin

    async def logout(self, *, refresh_token: str | None, response: Response) -> None:
        if refresh_token:
            await self.repo.revoke_refresh(hash_token(refresh_token))
        response.delete_cookie(ADMIN_ACCESS_COOKIE)
        response.delete_cookie(ADMIN_REFRESH_COOKIE, path=ADMIN_REFRESH_COOKIE_PATH)

    async def refresh(self, *, refresh_token: str, response: Response) -> Admin:
        rec = await self.repo.get_refresh(hash_token(refresh_token))
        if not rec:
            raise UnauthorizedError("Sesja wygasła, zaloguj się ponownie")
        admin = await self.repo.get_by_id(rec.admin_id)
        if not admin or not admin.is_active:
            raise UnauthorizedError("Konto niedostępne")
        # Rotate — old refresh dead, new pair issued.
        await self.repo.revoke_refresh(hash_token(refresh_token))
        await self._issue_session(admin, response)
        return admin

    # ── internals ────────────────────────────────────────────────────
    async def _issue_session(self, admin: Admin, response: Response) -> None:
        # audit_security H: see candidates/service.py for the rationale —
        # token_type is the explicit kwarg now.
        access = create_access_token(
            subject=str(admin.id),
            extra_claims={"admin_id": str(admin.id)},
            token_type="admin",
        )
        raw_refresh, refresh_hash = create_refresh_token()
        expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
        await self.repo.save_refresh_token(admin.id, refresh_hash, expires_at)

        secure = settings.is_production
        response.set_cookie(
            ADMIN_ACCESS_COOKIE,
            access,
            httponly=True,
            secure=secure,
            samesite="lax",
            max_age=access_token_cookie_max_age(),
        )
        response.set_cookie(
            ADMIN_REFRESH_COOKIE,
            raw_refresh,
            httponly=True,
            secure=secure,
            samesite="lax",
            max_age=settings.refresh_token_expire_days * 86400,
            path=ADMIN_REFRESH_COOKIE_PATH,
        )
