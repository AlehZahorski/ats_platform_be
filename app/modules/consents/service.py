from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.base_service import BaseService
from app.core.exceptions import NotFoundError
from app.core.i18n import t
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
        language: str | None = None,
    ) -> list[Consent]:
        return await self.repository.list_by_company(
            company_id, active_only=active_only, language=language
        )

    async def get(self, consent_id: uuid.UUID, company_id: uuid.UUID) -> Consent:
        consent = await self.repository.get_by_id_and_company(consent_id, company_id)
        if not consent:
            raise NotFoundError(t("consents.not_found"))
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

    async def get_application_consents(self, application_id: uuid.UUID) -> list[ApplicationConsent]:
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
            raise NotFoundError(t("consents.application_not_found"))
        app.data_retention_until = data.data_retention_until
        await db.flush()
        return app

    # ── GDPR: anonymize candidate data ────────────────────────────────────────
    async def anonymize(
        self,
        application_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> AnonymizeResult:
        """audit_rodo_gdpr F-09 (right to be forgotten, art. 17 GDPR):
        anonymisation now removes **every** copy of the candidate's PII, not
        just the columns on `applications`. Previously the CV file stayed on
        disk, `cv_parse_jobs.raw_text` held the full CV text, `candidate_profile`
        kept the AI-derived headline/summary/LinkedIn/etc., and `candidate_job_matches`
        kept the LLM's `reasoning` which often contains the candidate's name.
        The cleanup covers all of those + the physical CV file on disk + the
        normalized lookup keys so the row can no longer be re-identified."""
        from app.modules.application_events.models import ApplicationEvent
        from app.modules.applications.models import (
            Application,
            ApplicationAnswer,
            CandidateJobMatch,
            CandidateProfile,
            CVParseJob,
        )
        from app.modules.jobs.models import Job
        from app.modules.notes.models import Note
        from app.services.file_storage import file_storage

        db = self.repository.db
        result = await db.execute(
            select(Application)
            .join(Job, Application.job_id == Job.id)
            .where(Application.id == application_id, Job.company_id == company_id)
        )
        app = result.scalar_one_or_none()
        if not app:
            raise NotFoundError(t("consents.application_not_found"))

        # 1. Delete the CV file from disk BEFORE we drop the URL on the row.
        if app.cv_url:
            try:
                file_storage.delete_cv(app.cv_url)
            except Exception:
                # Best-effort — disk failure here must not block the legal
                # obligation to anonymize the database row.
                pass

        # 2. Overwrite the identifying columns on the application itself.
        app.first_name = "Anonymized"
        app.last_name = "User"
        app.email = f"anon_{application_id}@deleted.invalid"
        # Lookup keys must also be cleared — they reveal the same PII otherwise.
        app.normalized_email = f"anon_{application_id}"
        app.phone = None
        app.normalized_phone = None
        app.cv_url = None

        # 3. Drop dependent rows that carry PII or AI-derived inferences.
        for model, where_col in [
            (ApplicationAnswer, ApplicationAnswer.application_id),
            (Note, Note.application_id),
            (CVParseJob, CVParseJob.application_id),
            (CandidateProfile, CandidateProfile.application_id),
            (CandidateJobMatch, CandidateJobMatch.application_id),
            (ApplicationEvent, ApplicationEvent.application_id),
        ]:
            await db.execute(model.__table__.delete().where(where_col == application_id))

        await db.flush()

        return AnonymizeResult(
            application_id=application_id,
            anonymized=True,
            message=t("consents.anonymized"),
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
            raise NotFoundError(t("consents.application_not_found"))

        await db.delete(app)
        await db.flush()
        return {"deleted": True, "application_id": str(application_id)}

    # ── GDPR: cleanup expired applications ────────────────────────────────────
    async def cleanup_expired(self, company_id: uuid.UUID) -> dict:
        from app.modules.applications.models import Application
        from app.modules.jobs.models import Job

        db = self.repository.db
        now = datetime.now(UTC)
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
