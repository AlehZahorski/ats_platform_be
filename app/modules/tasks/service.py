from __future__ import annotations

import uuid
from typing import Optional

from app.core.base_service import BaseService
from app.core.exceptions import NotFoundError
from app.modules.tasks.models import Task
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.schemas import TaskCreate, TaskUpdate


class TaskService(BaseService[TaskRepository]):

    async def create(
        self, company_id: uuid.UUID, created_by: uuid.UUID, data: TaskCreate
    ) -> Task:
        return await self.repository.create(company_id, created_by, data)

    async def get(self, task_id: uuid.UUID, company_id: uuid.UUID) -> Task:
        task = await self.repository.get_by_id_and_company(task_id, company_id)
        if not task:
            raise NotFoundError("Task not found.")
        return task

    async def list(
        self,
        company_id: uuid.UUID,
        assigned_to: Optional[uuid.UUID] = None,
        completed: Optional[bool] = None,
        application_id: Optional[uuid.UUID] = None,
    ) -> list[Task]:
        return await self.repository.list_by_company(
            company_id,
            assigned_to=assigned_to,
            completed=completed,
            application_id=application_id,
        )

    async def update(self, task_id: uuid.UUID, company_id: uuid.UUID, data: TaskUpdate) -> Task:
        task = await self.get(task_id, company_id)
        return await self.repository.update(task, data)

    async def delete(self, task_id: uuid.UUID, company_id: uuid.UUID) -> None:
        task = await self.get(task_id, company_id)
        await self.repository.delete(task)
