"""Repositories for jobs module.

This module contains four focused repositories living in the same file (their
domain is closely tied to ``Job``):

1. ``JobRepository``              — CRUD for Job + form template link
2. ``AnalysisRepository``         — upsert for JobAnalysis + JobRiskAssessment (1:1 with Job)
3. ``RiskItemRepository``         — CRUD for user-entered risk items (1:N)
4. ``MitigationActionRepository`` — CRUD for user-entered mitigation actions (1:N)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base_repository import BaseRepository
from app.core.enums.jobs import JobStatus
from app.modules.jobs.analysis_models import JobAnalysis, JobRiskAssessment
from app.modules.jobs.models import Job, JobFormTemplate, MitigationAction, RiskItem
from app.modules.jobs.schemas import (
    JobCreate,
    JobUpdate,
    MitigationActionCreate,
    MitigationActionUpdate,
    RiskItemCreate,
    RiskItemUpdate,
)

# Sentinel for "field not in update payload" (None is a valid value for nullable fields).
_MISSING = object()


# ───────────────────────────────────────────────────────────────────────────
# JobRepository — CRUD + form template link
# ───────────────────────────────────────────────────────────────────────────


class JobRepository(BaseRepository[Job]):
    model = Job

    async def create(self, company_id: uuid.UUID, data: JobCreate) -> Job:
        job = Job(company_id=company_id, **data.model_dump(exclude={"template_id"}))
        self.db.add(job)
        await self.db.flush()

        if data.template_id:
            self.db.add(JobFormTemplate(job_id=job.id, template_id=data.template_id))
            await self.db.flush()

        return await self._load(job.id, company_id)  # type: ignore[return-value]

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

        total = (
            await self.db.execute(select(func.count()).select_from(query.subquery()))
        ).scalar_one()
        items = (
            (
                await self.db.execute(
                    query.offset(skip)
                    .limit(limit)
                    .order_by(Job.created_at.desc())
                    .options(*self._eager_load_options())
                )
            )
            .scalars()
            .all()
        )

        return list(items), total

    async def update(self, job: Job, data: JobUpdate) -> Job:
        payload = data.model_dump(exclude_unset=True)
        template_id = payload.pop("template_id", _MISSING)

        for field, value in payload.items():
            setattr(job, field, value)
        await self.db.flush()

        if template_id is not _MISSING:
            await self._update_template(job.id, template_id)  # type: ignore[arg-type]

        return await self._load(job.id, job.company_id)  # type: ignore[return-value]

    async def assign_template(self, job_id: uuid.UUID, template_id: uuid.UUID | None) -> None:
        await self._update_template(job_id, template_id)

    # ── Private helpers ───────────────────────────────────────────────────

    @staticmethod
    def _eager_load_options() -> tuple:
        return (
            selectinload(Job.form_template_link),
            selectinload(Job.analysis),
            selectinload(Job.risk_assessment),
            selectinload(Job.risk_items),
            selectinload(Job.mitigation_actions),
        )

    async def _load(self, job_id: uuid.UUID, company_id: uuid.UUID) -> Job | None:
        result = await self.db.execute(
            select(Job)
            .where(Job.id == job_id, Job.company_id == company_id)
            .options(*self._eager_load_options())
        )
        return result.scalar_one_or_none()

    async def _update_template(self, job_id: uuid.UUID, template_id: uuid.UUID | None) -> None:
        existing = (
            await self.db.execute(select(JobFormTemplate).where(JobFormTemplate.job_id == job_id))
        ).scalar_one_or_none()

        if template_id is None:
            if existing:
                await self.db.delete(existing)
        else:
            if existing:
                existing.template_id = template_id
            else:
                self.db.add(JobFormTemplate(job_id=job_id, template_id=template_id))
        await self.db.flush()


# ───────────────────────────────────────────────────────────────────────────
# AnalysisRepository — upsert for JobAnalysis + JobRiskAssessment (1:1)
# ───────────────────────────────────────────────────────────────────────────


class AnalysisRepository:
    """Upsert AI results into the 1:1 analysis tables.

    Both analyses are 1:1 with Job — at most one row per job. ``upsert_*``
    creates a new row if none exists, otherwise updates the existing one,
    and always refreshes the ``analyzed_at`` / ``assessed_at`` timestamp.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_analysis(self, job_id: uuid.UUID) -> JobAnalysis | None:
        return (
            await self.db.execute(select(JobAnalysis).where(JobAnalysis.job_id == job_id))
        ).scalar_one_or_none()

    async def get_risk_assessment(self, job_id: uuid.UUID) -> JobRiskAssessment | None:
        return (
            await self.db.execute(
                select(JobRiskAssessment).where(JobRiskAssessment.job_id == job_id)
            )
        ).scalar_one_or_none()

    async def upsert_analysis(self, job_id: uuid.UUID, data: dict[str, Any]) -> JobAnalysis:
        existing = await self.get_analysis(job_id)
        now = datetime.now(UTC)

        if existing is None:
            row = JobAnalysis(job_id=job_id, analyzed_at=now, **data)
            self.db.add(row)
        else:
            for key, value in data.items():
                setattr(existing, key, value)
            existing.analyzed_at = now
            row = existing

        await self.db.flush()
        return row

    async def upsert_risk_assessment(
        self, job_id: uuid.UUID, data: dict[str, Any]
    ) -> JobRiskAssessment:
        existing = await self.get_risk_assessment(job_id)
        now = datetime.now(UTC)

        if existing is None:
            row = JobRiskAssessment(job_id=job_id, assessed_at=now, **data)
            self.db.add(row)
        else:
            for key, value in data.items():
                setattr(existing, key, value)
            existing.assessed_at = now
            row = existing

        await self.db.flush()
        return row


# ───────────────────────────────────────────────────────────────────────────
# RiskItemRepository — CRUD for user-entered risk items (1:N)
# ───────────────────────────────────────────────────────────────────────────


class RiskItemRepository(BaseRepository[RiskItem]):
    model = RiskItem

    async def list_for_job(self, job_id: uuid.UUID) -> list[RiskItem]:
        result = await self.db.execute(
            select(RiskItem).where(RiskItem.job_id == job_id).order_by(RiskItem.order)
        )
        return list(result.scalars().all())

    async def get_by_id_and_job(self, item_id: uuid.UUID, job_id: uuid.UUID) -> RiskItem | None:
        result = await self.db.execute(
            select(RiskItem).where(RiskItem.id == item_id, RiskItem.job_id == job_id)
        )
        return result.scalar_one_or_none()

    async def add(self, job_id: uuid.UUID, data: RiskItemCreate) -> RiskItem:
        item = RiskItem(job_id=job_id, **data.model_dump())
        self.db.add(item)
        await self.db.flush()
        await self.db.refresh(item)
        return item

    async def update(self, item: RiskItem, data: RiskItemUpdate) -> RiskItem:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(item, field, value)
        await self.db.flush()
        await self.db.refresh(item)
        return item


# ───────────────────────────────────────────────────────────────────────────
# MitigationActionRepository — CRUD for user-entered mitigation actions (1:N)
# ───────────────────────────────────────────────────────────────────────────


class MitigationActionRepository(BaseRepository[MitigationAction]):
    model = MitigationAction

    async def list_for_job(self, job_id: uuid.UUID) -> list[MitigationAction]:
        result = await self.db.execute(
            select(MitigationAction)
            .where(MitigationAction.job_id == job_id)
            .order_by(MitigationAction.order)
        )
        return list(result.scalars().all())

    async def get_by_id_and_job(
        self, action_id: uuid.UUID, job_id: uuid.UUID
    ) -> MitigationAction | None:
        result = await self.db.execute(
            select(MitigationAction).where(
                MitigationAction.id == action_id,
                MitigationAction.job_id == job_id,
            )
        )
        return result.scalar_one_or_none()

    async def add(self, job_id: uuid.UUID, data: MitigationActionCreate) -> MitigationAction:
        action = MitigationAction(job_id=job_id, **data.model_dump())
        self.db.add(action)
        await self.db.flush()
        await self.db.refresh(action)
        return action

    async def update(
        self, action: MitigationAction, data: MitigationActionUpdate
    ) -> MitigationAction:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(action, field, value)
        await self.db.flush()
        await self.db.refresh(action)
        return action
