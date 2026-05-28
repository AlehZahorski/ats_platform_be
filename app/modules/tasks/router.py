import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentCompany, CurrentUser
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.schemas import TaskCreate, TaskRead, TaskUpdate
from app.modules.tasks.service import TaskService

router = APIRouter()


def _get_service(db: AsyncSession = Depends(get_db)) -> TaskService:
    return TaskService(TaskRepository(db))


@router.post("", response_model=TaskRead, status_code=201)
async def create_task(
    data: TaskCreate,
    company: CurrentCompany,
    user: CurrentUser,
    service: TaskService = Depends(_get_service),
) -> TaskRead:
    task = await service.create(company.id, user, data)
    return TaskRead.model_validate(task)


@router.get("", response_model=list[TaskRead])
async def list_tasks(
    company: CurrentCompany,
    user: CurrentUser,
    assigned_to_me: bool = Query(False),
    completed: Optional[bool] = Query(None),
    application_id: Optional[uuid.UUID] = Query(None),
    service: TaskService = Depends(_get_service),
) -> list[TaskRead]:
    tasks = await service.list(
        company_id=company.id,
        assigned_to=user.id if assigned_to_me else None,
        completed=completed,
        application_id=application_id,
    )
    return [TaskRead.model_validate(t) for t in tasks]


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: uuid.UUID,
    data: TaskUpdate,
    company: CurrentCompany,
    user: CurrentUser,
    service: TaskService = Depends(_get_service),
) -> TaskRead:
    task = await service.update(task_id, company.id, data, actor=user)
    return TaskRead.model_validate(task)


@router.delete("/{task_id}", status_code=204)
async def delete_task(
    task_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    service: TaskService = Depends(_get_service),
) -> Response:
    await service.delete(task_id, company.id)
    return Response(status_code=204)
