import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import CurrentCompany, CurrentUser
from app.core.exceptions import DuplicateDetectedError
from app.modules.applications.duplicate_service import DuplicateCheckService
from app.modules.applications.repository import ApplicationRepository
from app.modules.applications.schemas import (
    ApplicationList,
    ApplicationRead,
    ApplicationTrackingRead,
    BulkAction,
    BulkResult,
    CVParseConfirmPayload,
    CVParseJobRead,
    DuplicateCheckRequest,
    DuplicateCheckResponse,
    ScoreCreate,
    ScoreRead,
)
from app.modules.applications.service import ApplicationService
from app.modules.audit.service import AuditService
from app.modules.pipeline.repository import PipelineRepository

router = APIRouter()


def _get_service(db: AsyncSession = Depends(get_db)) -> ApplicationService:
    return ApplicationService(
        repository=ApplicationRepository(db),
        pipeline_repo=PipelineRepository(db),
        audit=AuditService(db),
        duplicate_svc=DuplicateCheckService(db),
        db=db,
    )


# ──────────────────────────────────────────────
# Public: candidate submits application
# ──────────────────────────────────────────────
@router.post("/apply/{job_id}", status_code=201)
async def apply(
    job_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    phone: Optional[str] = Form(None),
    answers: Optional[str] = Form(None),
    cv_file: Optional[UploadFile] = File(None),
    ignore_duplicate_warning: bool = Form(False),
    service: ApplicationService = Depends(_get_service),
) -> ApplicationRead:
    try:
        submit_result = await service.submit_application(
            job_id=job_id,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            raw_answers=answers,
            cv_file=cv_file,
            ignore_duplicate_warning=ignore_duplicate_warning,
            background_tasks=background_tasks,
            frontend_url=settings.frontend_url,
        )
    except DuplicateDetectedError as exc:
        return JSONResponse(
            status_code=409,
            content={
                "detail": {
                    "code": "duplicate_candidate_detected",
                    **exc.duplicate_response.model_dump(mode="json"),
                }
            },
        )
    return ApplicationRead.model_validate(submit_result.application)


@router.post("/duplicate-check", response_model=DuplicateCheckResponse)
async def duplicate_check(
    data: DuplicateCheckRequest,
    service: ApplicationService = Depends(_get_service),
) -> DuplicateCheckResponse:
    return await service.check_duplicate(data)


# ──────────────────────────────────────────────
# Public: candidate tracks own application
# ──────────────────────────────────────────────
@router.get("/track/{token}", response_model=ApplicationTrackingRead)
async def track_application(
    token: str,
    service: ApplicationService = Depends(_get_service),
) -> ApplicationTrackingRead:
    return await service.track_application(token)


# ──────────────────────────────────────────────
# HR: list applications
# ──────────────────────────────────────────────
@router.get("", response_model=ApplicationList)
async def list_applications(
    company: CurrentCompany,
    _user: CurrentUser,
    job_id: Optional[uuid.UUID] = Query(None),
    stage_id: Optional[uuid.UUID] = Query(None),
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    service: ApplicationService = Depends(_get_service),
) -> ApplicationList:
    return await service.list_applications(
        company_id=company.id,
        job_id=job_id,
        stage_id=stage_id,
        search=search,
        skip=skip,
        limit=limit,
    )


# ──────────────────────────────────────────────
# HR: single application detail
# ──────────────────────────────────────────────
@router.get("/{application_id}", response_model=ApplicationRead)
async def get_application(
    application_id: uuid.UUID,
    _company: CurrentCompany,
    _user: CurrentUser,
    service: ApplicationService = Depends(_get_service),
) -> ApplicationRead:
    return await service.get_application_detail(application_id)


@router.get("/{application_id}/cv-parse", response_model=CVParseJobRead | None)
async def get_cv_parse_status(
    application_id: uuid.UUID,
    _company: CurrentCompany,
    _user: CurrentUser,
    service: ApplicationService = Depends(_get_service),
) -> CVParseJobRead | None:
    return await service.get_cv_parse_status(application_id)


@router.post("/{application_id}/cv-parse/retry", response_model=CVParseJobRead)
async def retry_cv_parse(
    application_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    _company: CurrentCompany,
    _user: CurrentUser,
    service: ApplicationService = Depends(_get_service),
) -> CVParseJobRead:
    return await service.retry_cv_parse(application_id, background_tasks)


@router.post("/{application_id}/cv-parse/confirm", response_model=ApplicationRead)
async def confirm_cv_parse(
    application_id: uuid.UUID,
    data: CVParseConfirmPayload,
    _company: CurrentCompany,
    _user: CurrentUser,
    service: ApplicationService = Depends(_get_service),
) -> ApplicationRead:
    return await service.confirm_cv_parse(application_id, data)


# ──────────────────────────────────────────────
# HR: score a candidate
# ──────────────────────────────────────────────
@router.post("/{application_id}/score", response_model=ScoreRead)
async def score_application(
    application_id: uuid.UUID,
    data: ScoreCreate,
    _company: CurrentCompany,
    user: CurrentUser,
    service: ApplicationService = Depends(_get_service),
) -> ScoreRead:
    return await service.score_application(application_id, user.id, data)


# ──────────────────────────────────────────────
# HR: bulk operations
# ──────────────────────────────────────────────
@router.post("/bulk", response_model=BulkResult)
async def bulk_action(
    data: BulkAction,
    background_tasks: BackgroundTasks,
    company: CurrentCompany,
    user: CurrentUser,
    service: ApplicationService = Depends(_get_service),
) -> BulkResult:
    return await service.bulk_action(
        data=data,
        company_id=company.id,
        user_id=user.id,
        background_tasks=background_tasks,
        frontend_url=settings.frontend_url,
        company_name=company.name,
    )
