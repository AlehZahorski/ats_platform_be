from __future__ import annotations

import uuid

from app.core.base_service import BaseService
from app.core.enums.interviews import InterviewStatus
from app.core.exceptions import NotFoundError, UnprocessableError
from app.core.i18n import t
from app.core.ownership import ensure_application_in_company
from app.modules.application_events.models import ApplicationEvent
from app.modules.audit.service import AuditService
from app.modules.interviews.models import Interview
from app.modules.interviews.repository import InterviewRepository
from app.modules.interviews.schemas import InterviewCreate, InterviewUpdate


class InterviewService(BaseService[InterviewRepository]):
    def __init__(self, repository: InterviewRepository, audit: AuditService) -> None:
        super().__init__(repository)
        self.audit = audit

    async def create(
        self,
        application_id: uuid.UUID,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        data: InterviewCreate,
    ) -> Interview:
        await ensure_application_in_company(self.repository.db, application_id, company_id)
        self._validate_meeting_url(data.meeting_url, data.status)
        interview = await self.repository.create(application_id, data)

        self.audit.db.add(
            ApplicationEvent(
                application_id=application_id,
                company_id=company_id,
                event_type="interview_scheduled",
                event_value=str(interview.scheduled_at),
                metadata_={"interview_id": str(interview.id), "meeting_url": interview.meeting_url},
            )
        )
        await self.audit.log(
            company_id=company_id,
            user_id=user_id,
            action="interview_scheduled",
            entity_type="application",
            entity_id=application_id,
        )
        return interview

    async def get(self, interview_id: uuid.UUID) -> Interview:
        interview = await self.repository.get_by_id(interview_id)
        if not interview:
            raise NotFoundError(t("interviews.not_found"))
        return interview

    async def list_by_application(
        self, application_id: uuid.UUID, company_id: uuid.UUID
    ) -> list[Interview]:
        await ensure_application_in_company(self.repository.db, application_id, company_id)
        return await self.repository.list_by_application(application_id)

    async def update(
        self, interview_id: uuid.UUID, company_id: uuid.UUID, data: InterviewUpdate
    ) -> Interview:
        interview = await self.get(interview_id)
        await ensure_application_in_company(
            self.repository.db, interview.application_id, company_id
        )
        next_status = data.status or interview.status
        next_url = data.meeting_url if data.meeting_url is not None else interview.meeting_url
        self._validate_meeting_url(next_url, next_status)
        return await self.repository.update(interview, data)

    async def delete(
        self, interview_id: uuid.UUID, company_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        interview = await self.get(interview_id)
        await ensure_application_in_company(
            self.repository.db, interview.application_id, company_id
        )
        await self.audit.log(
            company_id=company_id,
            user_id=user_id,
            action="interview_deleted",
            entity_type="interview",
            entity_id=interview_id,
        )
        await self.repository.delete(interview)

    @staticmethod
    def _validate_meeting_url(meeting_url: str | None, status: InterviewStatus | None) -> None:
        if status != InterviewStatus.cancelled and not meeting_url:
            raise UnprocessableError(t("interviews.needs_link"))
