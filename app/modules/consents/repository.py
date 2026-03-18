from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.consents.models import ApplicationConsent, Consent
from app.modules.consents.schemas import (
    ApplicationConsentCreate,
    ConsentCreate,
    ConsentUpdate,
)


class ConsentRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Consent definitions ────────────────────────────────────────────────────
    async def create(self, company_id: uuid.UUID, data: ConsentCreate) -> Consent:
        consent = Consent(company_id=company_id, **data.model_dump())
        self.db.add(consent)
        await self.db.flush()
        await self.db.refresh(consent)
        return consent

    async def get_by_id(self, consent_id: uuid.UUID, company_id: uuid.UUID) -> Optional[Consent]:
        result = await self.db.execute(
            select(Consent).where(
                Consent.id == consent_id,
                Consent.company_id == company_id,
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        company_id: uuid.UUID,
        active_only: bool = False,
        language: Optional[str] = None,
    ) -> list[Consent]:
        query = select(Consent).where(Consent.company_id == company_id)
        if active_only:
            query = query.where(Consent.is_active.is_(True))
        if language:
            query = query.where(Consent.language == language)
        query = query.order_by(Consent.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update(self, consent: Consent, data: ConsentUpdate) -> Consent:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(consent, field, value)
        await self.db.flush()
        await self.db.refresh(consent)
        return consent

    async def delete(self, consent: Consent) -> None:
        await self.db.delete(consent)
        await self.db.flush()

    # ── Application consents ───────────────────────────────────────────────────
    async def record_consent(
        self,
        application_id: uuid.UUID,
        data: ApplicationConsentCreate,
    ) -> ApplicationConsent:
        # Upsert — update if already exists
        result = await self.db.execute(
            select(ApplicationConsent).where(
                ApplicationConsent.application_id == application_id,
                ApplicationConsent.consent_id == data.consent_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.accepted = data.accepted
            await self.db.flush()
            return existing

        record = ApplicationConsent(
            application_id=application_id,
            consent_id=data.consent_id,
            accepted=data.accepted,
        )
        self.db.add(record)
        await self.db.flush()
        return record

    async def get_application_consents(
        self, application_id: uuid.UUID
    ) -> list[ApplicationConsent]:
        result = await self.db.execute(
            select(ApplicationConsent)
            .where(ApplicationConsent.application_id == application_id)
            .options(selectinload(ApplicationConsent.consent))
        )
        return list(result.scalars().all())