from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.tasks.models import Task
from app.modules.tasks.schemas import TaskCreate, TaskUpdate


class TaskRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self, company_id: uuid.UUID, created_by: uuid.UUID, data: TaskCreate
    ) -> Task:
        task = Task(
            company_id=company_id,
            created_by=created_by,
            **data.model_dump(),
        )
        self.db.add(task)
        await self.db.flush()
        return await self._load(task.id)

    async def get_by_id(self, task_id: uuid.UUID, company_id: uuid.UUID) -> Optional[Task]:
        result = await self.db.execute(
            select(Task)
            .where(Task.id == task_id, Task.company_id == company_id)
            .options(
                selectinload(Task.assignee),
                selectinload(Task.creator),
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        company_id: uuid.UUID,
        assigned_to: Optional[uuid.UUID] = None,
        completed: Optional[bool] = None,
        application_id: Optional[uuid.UUID] = None,
    ) -> list[Task]:
        query = (
            select(Task)
            .where(Task.company_id == company_id)
            .options(selectinload(Task.assignee), selectinload(Task.creator))
        )
        if assigned_to:
            query = query.where(Task.assigned_to == assigned_to)
        if completed is not None:
            query = query.where(Task.completed == completed)
        if application_id:
            query = query.where(Task.application_id == application_id)
        query = query.order_by(Task.due_date.asc().nullslast(), Task.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update(self, task: Task, data: TaskUpdate) -> Task:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(task, field, value)
        if data.completed is True and not task.completed_at:
            task.completed_at = datetime.now(timezone.utc)
        elif data.completed is False:
            task.completed_at = None
        await self.db.flush()
        return await self._load(task.id)

    async def delete(self, task: Task) -> None:
        await self.db.delete(task)
        await self.db.flush()

    async def _load(self, task_id: uuid.UUID) -> Optional[Task]:
        result = await self.db.execute(
            select(Task)
            .where(Task.id == task_id)
            .options(selectinload(Task.assignee), selectinload(Task.creator))
        )
        return result.scalar_one_or_none()