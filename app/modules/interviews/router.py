import uuid

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any

from app.core.database import get_db
from app.core.dependencies import CurrentCompany, CurrentUser
from app.modules.interviews.schemas import InterviewCreate, InterviewRead, InterviewUpdate
from app.modules.interviews.service import InterviewService

router = APIRouter()


def _svc(db: AsyncSession = Depends(get_db)) -> InterviewService:
    return InterviewService(db)


@router.post(
    "/applications/{application_id}/interviews",
    response_model=InterviewRead,
    status_code=201,
)
async def schedule_interview(
    application_id: uuid.UUID,
    data: InterviewCreate,
    background_tasks: BackgroundTasks,
    company: CurrentCompany,
    user: CurrentUser,
    svc: InterviewService = Depends(_svc),
) -> InterviewRead:
    interview = await svc.create(
        application_id=application_id,
        company_id=company.id,
        user_id=user.id,
        data=data,
        background_tasks=background_tasks,
    )
    return InterviewRead.model_validate(interview)


@router.get(
    "/applications/{application_id}/interviews",
    response_model=list[InterviewRead],
)
async def list_interviews(
    application_id: uuid.UUID,
    _company: CurrentCompany,
    _user: CurrentUser,
    svc: InterviewService = Depends(_svc),
) -> list[InterviewRead]:
    interviews = await svc.list_by_application(application_id)
    return [InterviewRead.model_validate(i) for i in interviews]


@router.patch("/interviews/{interview_id}", response_model=InterviewRead)
async def update_interview(
    interview_id: uuid.UUID,
    data: InterviewUpdate,
    _company: CurrentCompany,
    _user: CurrentUser,
    svc: InterviewService = Depends(_svc),
) -> InterviewRead:
    interview = await svc.update(interview_id, data)
    return InterviewRead.model_validate(interview)


@router.delete("/interviews/{interview_id}")
async def delete_interview(
    interview_id: uuid.UUID,
    company: CurrentCompany,
    user: CurrentUser,
    svc: InterviewService = Depends(_svc),
) -> Response:
    await svc.delete(interview_id, company.id, user.id)
    return Response(status_code=204)
