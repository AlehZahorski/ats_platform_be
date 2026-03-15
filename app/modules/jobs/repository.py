from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.jobs.models import Job, JobFormTemplate
from app.modules.jobs.schemas import JobCreate, JobUpdate


class JobRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, company_id: uuid.UUID, data: JobCreate) -> Job:
        job = Job(
            company_id=company_id,
            **data.model_dump(exclude={"template_id"}),
        )
        self.db.add(job)
        await self.db.flush()

        if data.template_id:
            link = JobFormTemplate(job_id=job.id, template_id=data.template_id)
            self.db.add(link)
            await self.db.flush()

        await self.db.refresh(job)
        return job

    async def get_by_id(self, job_id: uuid.UUID, company_id: uuid.UUID) -> Job | None:
        result = await self.db.execute(
            select(Job).where(Job.id == job_id, Job.company_id == company_id)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        company_id: uuid.UUID,
        skip: int = 0,
        limit: int = 50,
        status: str | None = None,
    ) -> tuple[list[Job], int]:
        query = select(Job).where(Job.company_id == company_id)
        if status:
            query = query.where(Job.status == status)

        count_result = await self.db.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = count_result.scalar_one()

        result = await self.db.execute(query.offset(skip).limit(limit).order_by(Job.created_at.desc()))
        return list(result.scalars().all()), total

    async def update(self, job: Job, data: JobUpdate) -> Job:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(job, field, value)
        await self.db.flush()
        await self.db.refresh(job)
        return job

    async def delete(self, job: Job) -> None:
        await self.db.delete(job)
        await self.db.flush()
