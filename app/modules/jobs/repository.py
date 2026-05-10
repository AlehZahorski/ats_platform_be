from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.base_repository import BaseRepository
from app.core.enums.jobs import JobStatus
from app.modules.jobs.models import Job, JobFormTemplate
from app.modules.jobs.schemas import JobCreate, JobOfferAnalysisRead, JobUpdate


class JobRepository(BaseRepository[Job]):
    model = Job

    async def create(self, company_id: uuid.UUID, data: JobCreate) -> Job:
        job = Job(company_id=company_id, **data.model_dump(exclude={"template_id"}))
        self.db.add(job)
        await self.db.flush()

        if data.template_id:
            link = JobFormTemplate(job_id=job.id, template_id=data.template_id)
            self.db.add(link)
            await self.db.flush()

        return await self._load(job.id, company_id)

    async def get_by_id_and_company(self, job_id: uuid.UUID, company_id: uuid.UUID) -> Job | None:
        return await self._load(job_id, company_id)

    async def list_by_company(
        self,
        company_id: uuid.UUID,
        skip: int = 0,
        limit: int = 50,
        status: JobStatus | None = None,
    ) -> tuple[list[Job], int]:
        query = select(Job).where(Job.company_id == company_id)
        if status:
            query = query.where(Job.status == status)

        total = (await self.db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
        items = (
            await self.db.execute(
                query.offset(skip).limit(limit)
                .order_by(Job.created_at.desc())
                .options(selectinload(Job.form_template_link))
            )
        ).scalars().all()

        return list(items), total

    async def update(self, job: Job, data: JobUpdate) -> Job:
        for field, value in data.model_dump(exclude_unset=True, exclude={"template_id"}).items():
            setattr(job, field, value)
        await self.db.flush()

        if "template_id" in data.model_dump(exclude_unset=True):
            await self._update_template(job.id, data.template_id)

        return await self._load(job.id, job.company_id)

    async def assign_template(self, job_id: uuid.UUID, template_id: uuid.UUID | None) -> None:
        await self._update_template(job_id, template_id)

    async def save_analysis(self, job: Job, analysis: JobOfferAnalysisRead) -> None:
        job.analysis_score = analysis.attractiveness_score
        job.analysis_market_position = analysis.market_position
        job.analysis_summary = analysis.summary
        job.analysis_strengths = analysis.strengths
        job.analysis_improvements = analysis.improvements
        job.analysis_candidate_impact = analysis.candidate_impact
        job.analysis_urgency_message = analysis.urgency_message
        job.analysis_at = datetime.now(UTC)
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
