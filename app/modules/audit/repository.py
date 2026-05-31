from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.base_repository import BaseRepository
from app.modules.audit.models import AuditLog

# Force-import the related models so SQLAlchemy can resolve the string-FK
# relationships declared on AuditLog the moment this repository is loaded —
# avoids "could not find class 'User'" under some import orders.
from app.modules.companies.models import Company  # noqa: F401
from app.modules.users.models import User  # noqa: F401


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

        count_result = await self.db.execute(select(func.count()).select_from(query.subquery()))
        total = count_result.scalar_one()

        # audit_database P1/F-37: list view in the admin UI renders the actor
        # email per row. Without eager-loading we issued one `SELECT user`
        # per audit row. AuditLog now declares `user` / `company` relations
        # (see models.py) so selectinload avoids the N+1.
        result = await self.db.execute(
            query.options(
                selectinload(AuditLog.user),
                selectinload(AuditLog.company),
            )
            .order_by(AuditLog.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all()), total
