from __future__ import annotations

import uuid
from datetime import date as date_t
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.base_repository import BaseRepository
from app.modules.organizer.models import WorkSchedule
from app.modules.tasks.models import Task
from app.modules.users.models import User


class OrganizerRepository(BaseRepository[WorkSchedule]):
    model = WorkSchedule

    async def list_users(self, company_id: uuid.UUID, user_ids: Sequence[uuid.UUID]) -> list[User]:
        result = await self.db.execute(
            select(User)
            .where(User.company_id == company_id, User.id.in_(user_ids), User.is_active.is_(True))
            .order_by(User.email)
        )
        return list(result.scalars().all())

    async def list_active_company_users(self, company_id: uuid.UUID) -> list[User]:
        result = await self.db.execute(
            select(User)
            .where(User.company_id == company_id, User.is_active.is_(True))
            .order_by(User.email)
        )
        return list(result.scalars().all())

    async def list_schedules_in_range(
        self,
        company_id: uuid.UUID,
        user_ids: Sequence[uuid.UUID],
        start: date_t,
        end: date_t,
    ) -> list[WorkSchedule]:
        if not user_ids:
            return []
        result = await self.db.execute(
            select(WorkSchedule).where(
                WorkSchedule.company_id == company_id,
                WorkSchedule.user_id.in_(user_ids),
                WorkSchedule.date >= start,
                WorkSchedule.date <= end,
            )
        )
        return list(result.scalars().all())

    async def list_tasks_in_range(
        self,
        company_id: uuid.UUID,
        user_ids: Sequence[uuid.UUID],
        start: date_t,
        end: date_t,
    ) -> list[Task]:
        if not user_ids:
            return []
        result = await self.db.execute(
            select(Task)
            .where(
                Task.company_id == company_id,
                Task.assigned_to.in_(user_ids),
                Task.due_date.is_not(None),
            )
            .options(selectinload(Task.creator))
        )
        # Filter by date range in Python — Task.due_date is timestamp, comparing
        # to a date directly works in Postgres but keep type-safe here.
        out = []
        for task in result.scalars().all():
            if task.due_date is None:
                continue
            d = task.due_date.date()
            if start <= d <= end:
                out.append(task)
        return out

    async def get_schedule(
        self, company_id: uuid.UUID, user_id: uuid.UUID, day: date_t
    ) -> WorkSchedule | None:
        result = await self.db.execute(
            select(WorkSchedule)
            .where(
                WorkSchedule.company_id == company_id,
                WorkSchedule.user_id == user_id,
                WorkSchedule.date == day,
            )
            .options(selectinload(WorkSchedule.editor))
        )
        return result.scalar_one_or_none()

    async def list_tasks_for_user_day(
        self, company_id: uuid.UUID, user_id: uuid.UUID, day: date_t
    ) -> list[Task]:
        result = await self.db.execute(
            select(Task)
            .where(
                Task.company_id == company_id,
                Task.assigned_to == user_id,
                Task.due_date.is_not(None),
            )
            .options(selectinload(Task.creator))
            .order_by(Task.due_date.asc())
        )
        out = []
        for task in result.scalars().all():
            if task.due_date and task.due_date.date() == day:
                out.append(task)
        return out

    async def get_user(self, company_id: uuid.UUID, user_id: uuid.UUID) -> User | None:
        result = await self.db.execute(
            select(User).where(User.id == user_id, User.company_id == company_id)
        )
        return result.scalar_one_or_none()
