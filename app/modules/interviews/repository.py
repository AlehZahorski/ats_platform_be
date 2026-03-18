from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.interviews.models import Interview
from app.modules.interviews.schemas import InterviewCreate, InterviewUpdate


class InterviewRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, application_id: uuid.UUID, data: InterviewCreate) -> Interview:
        interview = Interview(application_id=application_id, **data.model_dump())
        self.db.add(interview)
        await self.db.flush()
        return await self._load(interview.id)

    async def get_by_id(self, interview_id: uuid.UUID) -> Optional[Interview]:
        return await self._load(interview_id)

    async def list_by_application(self, application_id: uuid.UUID) -> list[Interview]:
        result = await self.db.execute(
            select(Interview)
            .where(Interview.application_id == application_id)
            .options(selectinload(Interview.recruiter))
            .order_by(Interview.scheduled_at.asc())
        )
        return list(result.scalars().all())

    async def list_by_recruiter(self, recruiter_id: uuid.UUID) -> list[Interview]:
        result = await self.db.execute(
            select(Interview)
            .where(Interview.recruiter_id == recruiter_id)
            .options(selectinload(Interview.recruiter))
            .order_by(Interview.scheduled_at.asc())
        )
        return list(result.scalars().all())

    async def update(self, interview: Interview, data: InterviewUpdate) -> Interview:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(interview, field, value)
        await self.db.flush()
        return await self._load(interview.id)

    async def delete(self, interview: Interview) -> None:
        await self.db.delete(interview)
        await self.db.flush()

    async def _load(self, interview_id: uuid.UUID) -> Optional[Interview]:
        result = await self.db.execute(
            select(Interview)
            .where(Interview.id == interview_id)
            .options(selectinload(Interview.recruiter))
        )
        return result.scalar_one_or_none()
