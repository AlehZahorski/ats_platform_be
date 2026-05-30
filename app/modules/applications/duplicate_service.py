from __future__ import annotations

import re
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.applications.models import Application
from app.modules.applications.repository import ApplicationRepository
from app.modules.applications.schemas import DuplicateCheckMatch, DuplicateCheckResponse


def normalize_email(value: str) -> str:
    return value.strip().lower()


def normalize_phone(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.sub(r"\D+", "", value)
    return digits or None


def _mask_email(value: str | None) -> str | None:
    """audit_rodo_gdpr F-17: return ``j***@example.com`` from ``john@example.com``.

    Keeps the first character + the domain so the candidate recognises their
    own account but an attacker enumerating emails learns nothing new — they
    already supplied the email in the request.
    """
    if not value or "@" not in value:
        return None
    local, _, domain = value.partition("@")
    if not local:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"


class DuplicateCheckService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = ApplicationRepository(db)

    async def check(
        self,
        *,
        company_id: uuid.UUID,
        email: str,
        phone: str | None,
    ) -> DuplicateCheckResponse:
        normalized_email = normalize_email(email)
        normalized_phone = normalize_phone(phone)
        candidates = await self.repo.list_potential_duplicates(
            company_id=company_id,
            normalized_email=normalized_email,
            normalized_phone=normalized_phone,
        )

        matches: list[DuplicateCheckMatch] = []
        for application in candidates:
            reasons = self._collect_reasons(
                application=application,
                normalized_email=normalized_email,
                normalized_phone=normalized_phone,
            )
            if not reasons:
                continue

            # audit_rodo_gdpr F-17: this service powers the **public**
            # endpoint. Build a redacted match — only the URL token + a
            # masked email — so an attacker enumerating emails learns
            # nothing they did not already supply. HR-side callers that
            # legitimately need the full PII should query the application
            # repository directly with their company_id.
            matches.append(
                DuplicateCheckMatch(
                    application_id=application.id,
                    job_id=application.job_id,
                    public_token=application.public_token,
                    job_title=application.job.title if application.job else None,
                    masked_email=_mask_email(application.email),
                    created_at=application.created_at,
                    match_reasons=reasons,
                )
            )

        return DuplicateCheckResponse(
            has_duplicates=bool(matches),
            confidence="high" if matches else "none",
            matches=matches,
        )

    def _collect_reasons(
        self,
        *,
        application: Application,
        normalized_email: str,
        normalized_phone: str | None,
    ) -> list[str]:
        reasons: list[str] = []
        if application.normalized_email == normalized_email:
            reasons.append("email")
        if normalized_phone and self._phones_match(application.normalized_phone, normalized_phone):
            reasons.append("phone")
        return reasons

    def _phones_match(self, left: str | None, right: str) -> bool:
        if not left:
            return False
        if left == right:
            return True
        short_left = left[-9:] if len(left) >= 9 else left
        short_right = right[-9:] if len(right) >= 9 else right
        return short_left == short_right
