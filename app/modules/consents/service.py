from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.consents.repository import ConsentRepository
from app.modules.consents.schemas import (
    AnonymizeResult,
    ApplicationConsentCreate,
    ConsentCreate,
    ConsentUpdate,
    DataRetentionUpdate,
)


class ConsentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = ConsentRepository(db)

    # ── CRUD ──────────────────────────────────────────────────────────────────
    async def create(self, company_id: uuid.UUID, data: ConsentCreate):
        return await self.repo.create(company_id, data)

    async def list(self, company_id: uuid.UUID, active_only: bool = False, language: str | None = None):
        return await self.repo.list(company_id, active_only=active_only, language=language)

    async def get(self, consent_id: uuid.UUID, company_id: uuid.UUID):
        consent = await self.repo.get_by_id(consent_id, company_id)
        if not consent:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consent not found")
        return consent

    async def update(self, consent_id: uuid.UUID, company_id: uuid.UUID, data: ConsentUpdate):
        consent = await self.get(consent_id, company_id)
        return await self.repo.update(consent, data)

    async def delete(self, consent_id: uuid.UUID, company_id: uuid.UUID):
        consent = await self.get(consent_id, company_id)
        await self.repo.delete(consent)

    # ── Application consents ──────────────────────────────────────────────────
    async def record_application_consent(
        self, application_id: uuid.UUID, data: ApplicationConsentCreate
    ):
        return await self.repo.record_consent(application_id, data)

    async def get_application_consents(self, application_id: uuid.UUID):
        return await self.repo.get_application_consents(application_id)

    # ── GDPR: data retention ──────────────────────────────────────────────────
    async def set_retention(
        self,
        application_id: uuid.UUID,
        company_id: uuid.UUID,
        data: DataRetentionUpdate,
    ):
        from app.modules.applications.models import Application
        from app.modules.jobs.models import Job

        result = await self.db.execute(
            select(Application)
            .join(Job, Application.job_id == Job.id)
            .where(Application.id == application_id, Job.company_id == company_id)
        )
        app = result.scalar_one_or_none()
        if not app:
            raise HTTPException(status_code=404, detail="Application not found")
        app.data_retention_until = data.data_retention_until
        await self.db.flush()
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

        result = await self.db.execute(
            select(Application)
            .join(Job, Application.job_id == Job.id)
            .where(Application.id == application_id, Job.company_id == company_id)
        )
        app = result.scalar_one_or_none()
        if not app:
            raise HTTPException(status_code=404, detail="Application not found")

        # Overwrite PII with anonymized values
        app.first_name = "Anonymized"
        app.last_name = "User"
        app.email = f"anon_{application_id}@deleted.invalid"
        app.phone = None
        app.cv_url = None

        # Delete answers (may contain PII)
        await self.db.execute(
            ApplicationAnswer.__table__.delete().where(
                ApplicationAnswer.application_id == application_id
            )
        )

        # Delete notes
        await self.db.execute(
            Note.__table__.delete().where(Note.application_id == application_id)
        )

        await self.db.flush()

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

        result = await self.db.execute(
            select(Application)
            .join(Job, Application.job_id == Job.id)
            .where(Application.id == application_id, Job.company_id == company_id)
        )
        app = result.scalar_one_or_none()
        if not app:
            raise HTTPException(status_code=404, detail="Application not found")

        await self.db.delete(app)
        await self.db.flush()

        return {"deleted": True, "application_id": str(application_id)}

    # ── GDPR: cleanup expired applications ───────────────────────────────────
    async def cleanup_expired(self, company_id: uuid.UUID) -> dict:
        """Anonymize all applications past their retention date."""
        from app.modules.applications.models import Application
        from app.modules.jobs.models import Job

        now = datetime.now(timezone.utc)
        result = await self.db.execute(
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