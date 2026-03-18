import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentCompany, CurrentUser
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.schemas import TaskCreate, TaskRead, TaskUpdate

router = APIRouter()


def _repo(db: AsyncSession = Depends(get_db)) -> TaskRepository:
    return TaskRepository(db)


@router.post("", response_model=TaskRead, status_code=201)
async def create_task(
    data: TaskCreate,
    company: CurrentCompany,
    user: CurrentUser,
    repo: TaskRepository = Depends(_repo),
) -> TaskRead:
    task = await repo.create(company.id, user.id, data)
    return TaskRead.model_validate(task)


@router.get("", response_model=list[TaskRead])
async def list_tasks(
    company: CurrentCompany,
    user: CurrentUser,
    assigned_to_me: bool = Query(False),
    completed: Optional[bool] = Query(None),
    application_id: Optional[uuid.UUID] = Query(None),
    repo: TaskRepository = Depends(_repo),
) -> list[TaskRead]:
    tasks = await repo.list(
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
    _user: CurrentUser,
    repo: TaskRepository = Depends(_repo),
) -> TaskRead:
    task = await repo.get_by_id(task_id, company.id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task = await repo.update(task, data)
    return TaskRead.model_validate(task)


@router.delete("/{task_id}")
async def delete_task(
    task_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    repo: TaskRepository = Depends(_repo),
) -> Response:
    task = await repo.get_by_id(task_id, company.id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    await repo.delete(task)
    return Response(status_code=204)