from __future__ import annotations

import uuid

from app.core.base_service import BaseService
from app.core.enums.users import UserRole
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.i18n import t
from app.core.ownership import ensure_application_in_company
from app.modules.tasks.models import Task
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.schemas import TaskCreate, TaskUpdate
from app.modules.users.models import User


class TaskService(BaseService[TaskRepository]):
    @staticmethod
    def _can_assign(actor: User, target_user_id: uuid.UUID | None) -> bool:
        # Managers and owners can assign anyone in their company.
        # Recruiters can only assign to themselves (or no one).
        if actor.role in (UserRole.owner.value, UserRole.manager.value):
            return True
        if target_user_id is None:
            return True
        return target_user_id == actor.id

    async def create(self, company_id: uuid.UUID, actor: User, data: TaskCreate) -> Task:
        if not self._can_assign(actor, data.assigned_to):
            raise ForbiddenError(t("auth.role_not_permitted", role=actor.role))
        if data.application_id is not None:
            await ensure_application_in_company(
                self.repository.db, data.application_id, company_id
            )
        return await self.repository.create(company_id, actor.id, data)

    async def get(self, task_id: uuid.UUID, company_id: uuid.UUID) -> Task:
        task = await self.repository.get_by_id_and_company(task_id, company_id)
        if not task:
            raise NotFoundError(t("tasks.not_found"))
        return task

    async def list(
        self,
        company_id: uuid.UUID,
        assigned_to: uuid.UUID | None = None,
        completed: bool | None = None,
        application_id: uuid.UUID | None = None,
    ) -> list[Task]:
        return await self.repository.list_by_company(
            company_id,
            assigned_to=assigned_to,
            completed=completed,
            application_id=application_id,
        )

    async def update(
        self, task_id: uuid.UUID, company_id: uuid.UUID, data: TaskUpdate, actor: User | None = None
    ) -> Task:
        task = await self.get(task_id, company_id)
        if (
            actor is not None
            and data.assigned_to is not None
            and data.assigned_to != task.assigned_to
        ) and not self._can_assign(actor, data.assigned_to):
            raise ForbiddenError(t("auth.role_not_permitted", role=actor.role))
        if data.application_id is not None:
            await ensure_application_in_company(
                self.repository.db, data.application_id, company_id
            )
        return await self.repository.update(task, data)

    async def delete(self, task_id: uuid.UUID, company_id: uuid.UUID) -> None:
        task = await self.get(task_id, company_id)
        await self.repository.delete(task)
