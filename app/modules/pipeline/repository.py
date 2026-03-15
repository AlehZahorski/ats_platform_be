from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.pipeline.models import ApplicationStageHistory, PipelineStage


class PipelineRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_stages(self) -> list[PipelineStage]:
        result = await self.db.execute(
            select(PipelineStage).order_by(PipelineStage.order_index)
        )
        return list(result.scalars().all())

    async def get_stage(self, stage_id: uuid.UUID) -> PipelineStage | None:
        result = await self.db.execute(
            select(PipelineStage).where(PipelineStage.id == stage_id)
        )
        return result.scalar_one_or_none()

    async def record_stage_change(
        self,
        application_id: uuid.UUID,
        stage_id: uuid.UUID,
        changed_by: uuid.UUID,
    ) -> ApplicationStageHistory:
        history = ApplicationStageHistory(
            application_id=application_id,
            stage_id=stage_id,
            changed_by=changed_by,
        )
        self.db.add(history)
        await self.db.flush()
        # reload with stage relationship
        result = await self.db.execute(
            select(ApplicationStageHistory)
            .where(ApplicationStageHistory.id == history.id)
            .options(selectinload(ApplicationStageHistory.stage))
        )
        return result.scalar_one()

    async def get_history(self, application_id: uuid.UUID) -> list[ApplicationStageHistory]:
        result = await self.db.execute(
            select(ApplicationStageHistory)
            .where(ApplicationStageHistory.application_id == application_id)
            .options(selectinload(ApplicationStageHistory.stage))
            .order_by(ApplicationStageHistory.changed_at.asc())
        )
        return list(result.scalars().all())
