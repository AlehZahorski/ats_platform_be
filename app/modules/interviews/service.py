from __future__ import annotations

import uuid
from typing import Optional

from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.application_events.models import ApplicationEvent
from app.modules.audit.models import AuditLog
from app.modules.interviews.models import Interview
from app.modules.interviews.repository import InterviewRepository
from app.modules.interviews.schemas import InterviewCreate, InterviewUpdate


class InterviewService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = InterviewRepository(db)

    async def create(
        self,
        application_id: uuid.UUID,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        data: InterviewCreate,
        background_tasks: BackgroundTasks,
    ) -> Interview:
        interview = await self.repo.create(application_id, data)

        # Log application event
        event = ApplicationEvent(
            application_id=application_id,
            company_id=company_id,
            event_type="interview_scheduled",
            event_value=str(interview.scheduled_at),
            metadata_={
                "interview_id": str(interview.id),
                "meeting_url": interview.meeting_url,
            },
        )
        self.db.add(event)

        # Audit log
        audit = AuditLog(
            company_id=company_id,
            user_id=user_id,
            action="interview_scheduled",
            entity_type="application",
            entity_id=application_id,
        )
        self.db.add(audit)

        await self.db.flush()
        return interview

    async def list_by_application(self, application_id: uuid.UUID) -> list[Interview]:
        return await self.repo.list_by_application(application_id)

    async def get(self, interview_id: uuid.UUID) -> Interview:
        interview = await self.repo.get_by_id(interview_id)
        if not interview:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Interview not found"
            )
        return interview

    async def update(
        self,
        interview_id: uuid.UUID,
        data: InterviewUpdate,
    ) -> Interview:
        interview = await self.get(interview_id)
        return await self.repo.update(interview, data)

    async def delete(
        self,
        interview_id: uuid.UUID,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        interview = await self.get(interview_id)

        audit = AuditLog(
            company_id=company_id,
            user_id=user_id,
            action="interview_deleted",
            entity_type="interview",
            entity_id=interview_id,
        )
        self.db.add(audit)

        await self.repo.delete(interview)
