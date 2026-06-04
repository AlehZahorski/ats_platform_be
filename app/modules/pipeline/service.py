from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base_service import BaseService
from app.core.exceptions import ConflictError, NotFoundError, UnprocessableError
from app.core.i18n import t
from app.core.ownership import ensure_application_in_company
from app.modules.audit.service import AuditService
from app.modules.pipeline.models import ApplicationStageHistory, PipelineStage
from app.modules.pipeline.repository import PipelineRepository


@dataclass
class StageChangeContext:
    """Data returned from update_application_stage for the router to handle notifications."""

    history: ApplicationStageHistory
    candidate_email: str
    candidate_name: str
    job_title: str
    stage_name: str
    interview: Any | None
    tracking_token: str


class PipelineService(BaseService[PipelineRepository]):
    def __init__(
        self, repository: PipelineRepository, audit: AuditService, db: AsyncSession
    ) -> None:
        super().__init__(repository)
        self.audit = audit
        # Direct db access for cross-module queries until ApplicationRepository is refactored
        self.db = db

    async def create_stage(self, name: str) -> PipelineStage:
        name = name.strip()
        if not name:
            raise UnprocessableError(t("pipeline.stage_name_required"))
        return await self.repository.create_stage(name)

    async def rename_stage(self, stage_id: uuid.UUID, name: str) -> PipelineStage:
        stage = await self.repository.get_by_id(stage_id)
        if not stage:
            raise NotFoundError(t("pipeline.stage_not_found"))
        name = name.strip()
        if not name:
            raise UnprocessableError(t("pipeline.stage_name_required"))
        return await self.repository.update_stage_name(stage, name)

    async def reorder_stages(
        self, stage_orders: list[tuple[uuid.UUID, int]]
    ) -> list[PipelineStage]:
        existing_ids = {stage.id for stage in await self.repository.list_stages()}
        requested_ids = {stage_id for stage_id, _ in stage_orders}
        if existing_ids != requested_ids:
            raise UnprocessableError(t("pipeline.reorder_incomplete"))
        return await self.repository.reorder_stages(stage_orders)

    async def delete_stage(self, stage_id: uuid.UUID) -> None:
        stage = await self.repository.get_by_id(stage_id)
        if not stage:
            raise NotFoundError(t("pipeline.stage_not_found"))
        applications_count, history_count = await self.repository.stage_usage_counts(stage_id)
        if applications_count > 0 or history_count > 0:
            raise ConflictError(t("pipeline.stage_in_use"))
        await self.repository.delete(stage)

    async def update_application_stage(
        self,
        application_id: uuid.UUID,
        stage_id: uuid.UUID,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> StageChangeContext:
        from app.modules.applications.models import Application
        from app.modules.interviews.repository import InterviewRepository
        from app.modules.jobs.models import Job

        result = await self.db.execute(
            select(Application)
            .join(Job, Application.job_id == Job.id)
            .where(Application.id == application_id, Job.company_id == company_id)
        )
        application = result.scalar_one_or_none()
        if not application:
            raise NotFoundError(t("pipeline.application_not_found"))

        stage = await self.repository.get_by_id(stage_id)
        if not stage:
            raise NotFoundError(t("pipeline.stage_not_found"))

        interview = None
        if stage.name.strip().lower() == "interview":
            interview = await InterviewRepository(self.db).get_stage_ready_interview(application_id)
            if not interview:
                raise UnprocessableError(t("pipeline.interview_needs_link"))

        application.stage_id = stage.id
        await self.db.flush()

        history = await self.repository.record_stage_change(application_id, stage.id, user_id)

        await self.audit.log(
            company_id=company_id,
            user_id=user_id,
            action="candidate_moved_stage",
            entity_type="application",
            entity_id=application_id,
            metadata={"stage_name": stage.name},
        )

        job_result = await self.db.execute(select(Job).where(Job.id == application.job_id))
        job = job_result.scalar_one_or_none()

        return StageChangeContext(
            history=history,
            candidate_email=application.email,
            candidate_name=f"{application.first_name} {application.last_name}",
            job_title=job.title if job else "position",
            stage_name=stage.name,
            interview=interview,
            tracking_token=application.public_token,
        )

    async def get_history(
        self, application_id: uuid.UUID, company_id: uuid.UUID
    ) -> list[ApplicationStageHistory]:
        await ensure_application_in_company(self.db, application_id, company_id)
        return await self.repository.get_history(application_id)
