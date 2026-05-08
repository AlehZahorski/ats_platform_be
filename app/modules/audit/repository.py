from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.core.base_repository import BaseRepository
from app.modules.audit.models import AuditLog


class AuditRepository(BaseRepository[AuditLog]):
    model = AuditLog

    async def list(
        self,
        company_id: uuid.UUID,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[AuditLog], int]:
        query = select(AuditLog).where(AuditLog.company_id == company_id)

        if entity_type:
            query = query.where(AuditLog.entity_type == entity_type)
        if entity_id:
            query = query.where(AuditLog.entity_id == entity_id)

        count_result = await self.db.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = count_result.scalar_one()

        result = await self.db.execute(
            query.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total
