import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentCompany, CurrentUser
from app.modules.audit.service import AuditService
from app.modules.interviews.repository import InterviewRepository
from app.modules.interviews.schemas import InterviewCreate, InterviewRead, InterviewUpdate
from app.modules.interviews.service import InterviewService

router = APIRouter()


def _get_service(db: AsyncSession = Depends(get_db)) -> InterviewService:
    return InterviewService(InterviewRepository(db), AuditService(db))


@router.post(
    "/applications/{application_id}/interviews", response_model=InterviewRead, status_code=201
)
async def schedule_interview(
    application_id: uuid.UUID,
    data: InterviewCreate,
    company: CurrentCompany,
    user: CurrentUser,
    service: InterviewService = Depends(_get_service),
) -> InterviewRead:
    interview = await service.create(
        application_id=application_id,
        company_id=company.id,
        user_id=user.id,
        data=data,
    )
    return InterviewRead.model_validate(interview)


@router.get("/applications/{application_id}/interviews", response_model=list[InterviewRead])
async def list_interviews(
    application_id: uuid.UUID,
    _company: CurrentCompany,
    _user: CurrentUser,
    service: InterviewService = Depends(_get_service),
) -> list[InterviewRead]:
    interviews = await service.list_by_application(application_id)
    return [InterviewRead.model_validate(i) for i in interviews]


@router.patch("/interviews/{interview_id}", response_model=InterviewRead)
async def update_interview(
    interview_id: uuid.UUID,
    data: InterviewUpdate,
    _company: CurrentCompany,
    _user: CurrentUser,
    service: InterviewService = Depends(_get_service),
) -> InterviewRead:
    interview = await service.update(interview_id, data)
    return InterviewRead.model_validate(interview)


@router.delete("/interviews/{interview_id}", status_code=204)
async def delete_interview(
    interview_id: uuid.UUID,
    company: CurrentCompany,
    user: CurrentUser,
    service: InterviewService = Depends(_get_service),
) -> Response:
    await service.delete(interview_id, company.id, user.id)
    return Response(status_code=204)
