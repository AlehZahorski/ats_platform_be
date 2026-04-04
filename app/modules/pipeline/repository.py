from __future__ import annotations

import uuid

from sqlalchemy import func, select
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

    async def get_max_order_index(self) -> int:
        result = await self.db.execute(select(func.max(PipelineStage.order_index)))
        value = result.scalar_one()
        return value if value is not None else -1

    async def create_stage(self, name: str) -> PipelineStage:
        stage = PipelineStage(
            name=name,
            order_index=await self.get_max_order_index() + 1,
        )
        self.db.add(stage)
        await self.db.flush()
        return stage

    async def update_stage_name(self, stage: PipelineStage, name: str) -> PipelineStage:
        stage.name = name
        await self.db.flush()
        return stage

    async def reorder_stages(self, stage_orders: list[tuple[uuid.UUID, int]]) -> list[PipelineStage]:
        stage_map = {
            stage.id: stage
            for stage in await self.list_stages()
        }
        for stage_id, order_index in stage_orders:
            stage = stage_map.get(stage_id)
            if stage:
                stage.order_index = order_index
        await self.db.flush()
        return await self.list_stages()

    async def stage_usage_counts(self, stage_id: uuid.UUID) -> tuple[int, int]:
        from app.modules.applications.models import Application

        applications_result = await self.db.execute(
            select(func.count(Application.id)).where(Application.stage_id == stage_id)
        )
        history_result = await self.db.execute(
            select(func.count(ApplicationStageHistory.id)).where(ApplicationStageHistory.stage_id == stage_id)
        )
        return applications_result.scalar_one(), history_result.scalar_one()

    async def delete_stage(self, stage: PipelineStage) -> None:
        await self.db.delete(stage)
        await self.db.flush()

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
