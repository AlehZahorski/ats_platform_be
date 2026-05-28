from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import Response

from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError, UnauthorizedError
from app.core.i18n import t
from app.core.security import (
    access_token_cookie_max_age,
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.modules.candidates.models import Candidate
from app.modules.candidates.repository import CandidateRepository


# Cookie names — kept separate from the recruiter-side cookies so the two
# sessions can coexist in the same browser without stomping each other.
CANDIDATE_ACCESS_COOKIE = "candidate_access_token"
CANDIDATE_REFRESH_COOKIE = "candidate_refresh_token"


class CandidateAuthService:
    def __init__(self, repo: CandidateRepository) -> None:
        self.repo = repo

    async def signup(self, *, email: str, password: str, full_name: str | None, response: Response) -> Candidate:
        email_norm = email.strip().lower()
        if await self.repo.get_by_email(email_norm):
            raise ConflictError(t("auth.email_taken") if False else "Adres e-mail jest już zarejestrowany")
        candidate = await self.repo.create(
            email=email_norm,
            password_hash=hash_password(password),
            full_name=(full_name or "").strip() or None,
        )
        await self._issue_session(candidate, response)
        return candidate

    async def login(self, *, email: str, password: str, response: Response) -> Candidate:
        candidate = await self.repo.get_by_email(email.strip().lower())
        if not candidate or not verify_password(password, candidate.password_hash):
            raise UnauthorizedError("Nieprawidłowy e-mail lub hasło")
        if not candidate.is_active:
            raise UnauthorizedError("Konto zostało zdezaktywowane")
        await self._issue_session(candidate, response)
        return candidate

    async def logout(self, *, refresh_token: str | None, response: Response) -> None:
        if refresh_token:
            await self.repo.revoke_refresh(hash_token(refresh_token))
        response.delete_cookie(CANDIDATE_ACCESS_COOKIE)
        response.delete_cookie(CANDIDATE_REFRESH_COOKIE, path="/api/v1/candidates/refresh")

    async def refresh(self, *, refresh_token: str, response: Response) -> Candidate:
        rec = await self.repo.get_refresh(hash_token(refresh_token))
        if not rec:
            raise UnauthorizedError("Sesja wygasła, zaloguj się ponownie")
        candidate = await self.repo.get_by_id(rec.candidate_id)
        if not candidate or not candidate.is_active:
            raise UnauthorizedError("Konto niedostępne")
        # Rotate refresh token
        await self.repo.revoke_refresh(hash_token(refresh_token))
        await self._issue_session(candidate, response)
        return candidate

    async def update_profile(self, candidate: Candidate, updates: dict) -> Candidate:
        for key, value in updates.items():
            if value is not None:
                setattr(candidate, key, value)
        await self.repo.db.flush()
        return candidate

    # ── internals ──────────────────────────────────────────────────────────
    async def _issue_session(self, candidate: Candidate, response: Response) -> None:
        access = create_access_token(
            subject=str(candidate.id),
            extra_claims={"type": "candidate", "candidate_id": str(candidate.id)},
        )
        raw_refresh, refresh_hash = create_refresh_token()
        expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
        await self.repo.save_refresh_token(candidate.id, refresh_hash, expires_at)

        secure = settings.is_production
        response.set_cookie(
            CANDIDATE_ACCESS_COOKIE,
            access,
            httponly=True,
            secure=secure,
            samesite="lax",
            max_age=access_token_cookie_max_age(),
        )
        response.set_cookie(
            CANDIDATE_REFRESH_COOKIE,
            raw_refresh,
            httponly=True,
            secure=secure,
            samesite="lax",
            max_age=settings.refresh_token_expire_days * 86400,
            path="/api/v1/candidates/refresh",
        )
