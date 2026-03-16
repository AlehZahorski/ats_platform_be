from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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

        return await self._load(job.id, company_id)

    async def get_by_id(self, job_id: uuid.UUID, company_id: uuid.UUID) -> Job | None:
        return await self._load(job_id, company_id)

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

        result = await self.db.execute(
            query.offset(skip).limit(limit).order_by(Job.created_at.desc())
            .options(selectinload(Job.form_template_link))
        )
        return list(result.scalars().all()), total

    async def update(self, job: Job, data: JobUpdate) -> Job:
        exclude = {"template_id"}
        for field, value in data.model_dump(exclude_unset=True, exclude=exclude).items():
            setattr(job, field, value)
        await self.db.flush()

        # Handle template assignment change
        if "template_id" in data.model_dump(exclude_unset=True):
            await self._update_template(job.id, data.template_id)

        return await self._load(job.id, job.company_id)

    async def assign_template(self, job_id: uuid.UUID, template_id: uuid.UUID | None) -> None:
        await self._update_template(job_id, template_id)

    async def delete(self, job: Job) -> None:
        await self.db.delete(job)
        await self.db.flush()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    async def _load(self, job_id: uuid.UUID, company_id: uuid.UUID) -> Job | None:
        result = await self.db.execute(
            select(Job)
            .where(Job.id == job_id, Job.company_id == company_id)
            .options(selectinload(Job.form_template_link))
        )
        return result.scalar_one_or_none()

    async def _update_template(self, job_id: uuid.UUID, template_id: uuid.UUID | None) -> None:
        result = await self.db.execute(
            select(JobFormTemplate).where(JobFormTemplate.job_id == job_id)
        )
        existing = result.scalar_one_or_none()

        if template_id is None:
            if existing:
                await self.db.delete(existing)
        else:
            if existing:
                existing.template_id = template_id
            else:
                self.db.add(JobFormTemplate(job_id=job_id, template_id=template_id))
        await self.db.flush()