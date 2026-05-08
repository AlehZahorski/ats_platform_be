from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from app.core.base_service import BaseService
from app.core.exceptions import NotFoundError
from app.modules.consents.models import ApplicationConsent, Consent
from app.modules.consents.repository import ConsentRepository
from app.modules.consents.schemas import (
    AnonymizeResult,
    ApplicationConsentCreate,
    ConsentCreate,
    ConsentUpdate,
    DataRetentionUpdate,
)


class ConsentService(BaseService[ConsentRepository]):

    # ── CRUD ──────────────────────────────────────────────────────────────────
    async def create(self, company_id: uuid.UUID, data: ConsentCreate) -> Consent:
        return await self.repository.create(company_id, data)

    async def list(
        self,
        company_id: uuid.UUID,
        active_only: bool = False,
        language: Optional[str] = None,
    ) -> list[Consent]:
        return await self.repository.list_by_company(
            company_id, active_only=active_only, language=language
        )

    async def get(self, consent_id: uuid.UUID, company_id: uuid.UUID) -> Consent:
        consent = await self.repository.get_by_id_and_company(consent_id, company_id)
        if not consent:
            raise NotFoundError("Consent not found.")
        return consent

    async def update(
        self, consent_id: uuid.UUID, company_id: uuid.UUID, data: ConsentUpdate
    ) -> Consent:
        consent = await self.get(consent_id, company_id)
        return await self.repository.update(consent, data)

    async def delete(self, consent_id: uuid.UUID, company_id: uuid.UUID) -> None:
        consent = await self.get(consent_id, company_id)
        await self.repository.delete(consent)

    # ── Application consents ──────────────────────────────────────────────────
    async def record_application_consent(
        self, application_id: uuid.UUID, data: ApplicationConsentCreate
    ) -> ApplicationConsent:
        return await self.repository.record_consent(application_id, data)

    async def get_application_consents(
        self, application_id: uuid.UUID
    ) -> list[ApplicationConsent]:
        return await self.repository.get_application_consents(application_id)

    # ── GDPR: data retention ──────────────────────────────────────────────────
    async def set_retention(
        self,
        application_id: uuid.UUID,
        company_id: uuid.UUID,
        data: DataRetentionUpdate,
    ) -> object:
        from app.modules.applications.models import Application
        from app.modules.jobs.models import Job

        db = self.repository.db
        result = await db.execute(
            select(Application)
            .join(Job, Application.job_id == Job.id)
            .where(Application.id == application_id, Job.company_id == company_id)
        )
        app = result.scalar_one_or_none()
        if not app:
            raise NotFoundError("Application not found.")
        app.data_retention_until = data.data_retention_until
        await db.flush()
        return app

    # ── GDPR: anonymize candidate data ────────────────────────────────────────
    async def anonymize(
        self,
        application_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> AnonymizeResult:
        from app.modules.applications.models import Application, ApplicationAnswer
        from app.modules.jobs.models import Job
        from app.modules.notes.models import Note

        db = self.repository.db
        result = await db.execute(
            select(Application)
            .join(Job, Application.job_id == Job.id)
            .where(Application.id == application_id, Job.company_id == company_id)
        )
        app = result.scalar_one_or_none()
        if not app:
            raise NotFoundError("Application not found.")

        app.first_name = "Anonymized"
        app.last_name = "User"
        app.email = f"anon_{application_id}@deleted.invalid"
        app.phone = None
        app.cv_url = None

        await db.execute(
            ApplicationAnswer.__table__.delete().where(
                ApplicationAnswer.application_id == application_id
            )
        )
        await db.execute(
            Note.__table__.delete().where(Note.application_id == application_id)
        )
        await db.flush()

        return AnonymizeResult(
            application_id=application_id,
            anonymized=True,
            message="Candidate data has been anonymized successfully.",
        )

    # ── GDPR: hard delete ─────────────────────────────────────────────────────
    async def delete_application_data(
        self,
        application_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> dict:
        from app.modules.applications.models import Application
        from app.modules.jobs.models import Job

        db = self.repository.db
        result = await db.execute(
            select(Application)
            .join(Job, Application.job_id == Job.id)
            .where(Application.id == application_id, Job.company_id == company_id)
        )
        app = result.scalar_one_or_none()
        if not app:
            raise NotFoundError("Application not found.")

        await db.delete(app)
        await db.flush()
        return {"deleted": True, "application_id": str(application_id)}

    # ── GDPR: cleanup expired applications ────────────────────────────────────
    async def cleanup_expired(self, company_id: uuid.UUID) -> dict:
        from app.modules.applications.models import Application
        from app.modules.jobs.models import Job

        db = self.repository.db
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(Application)
            .join(Job, Application.job_id == Job.id)
            .where(
                Job.company_id == company_id,
                Application.data_retention_until.isnot(None),
                Application.data_retention_until <= now,
                Application.email.notlike("%@deleted.invalid"),
            )
        )
        expired = result.scalars().all()
        count = 0
        for app in expired:
            await self.anonymize(app.id, company_id)
            count += 1
        return {"anonymized": count}
