import uuid

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import CurrentCompany, CurrentUser
from app.core.exceptions import DuplicateDetectedError
from app.core.i18n import detect_language
from app.core.ownership import ensure_application_in_company
from app.core.rate_limit import rate_limit
from app.modules.applications.duplicate_service import DuplicateCheckService
from app.modules.applications.repository import ApplicationRepository
from app.modules.applications.schemas import (
    ApplicationEventRead,
    ApplicationList,
    ApplicationRead,
    ApplicationTrackingRead,
    BulkAction,
    BulkResult,
    CandidateJobMatchRead,
    # L1/M5 (audit_backend_code): CVParseConfirmPayload removed from this
    # import — the corresponding endpoint was never wired. The service method
    # `confirm_cv_parse` still exists for a planned "review-required" flow;
    # the schema stays available in `applications.schemas`.
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
# audit_security C3: rate-limit the public apply endpoint per IP. Without it
# a single client could flood the LLM pipeline + email notifier; 20/minute is
# enough for a legitimate flurry (e.g. an agency assistant doing data entry).
@router.post(
    "/apply/{job_id}",
    status_code=201,
    dependencies=[Depends(rate_limit("20/minute"))],
)
async def apply(
    request: Request,
    job_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    phone: str | None = Form(None),
    answers: str | None = Form(None),
    cv_file: UploadFile | None = File(None),
    ignore_duplicate_warning: bool = Form(False),
    # F-02 / audit_ai F-02 + audit_ai_ethics: explicit consent for AI profiling.
    # Default False — when the candidate did not tick the box, the backend
    # redacts PII (email, phone) before sending the CV to Anthropic and skips
    # the candidate↔job match call entirely. Recruiter still sees the regex
    # parse + the redacted enrichment.
    ai_profiling_consent: bool = Form(False),
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
            language=detect_language(request),
            ai_profiling_consent=ai_profiling_consent,
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


# ──────────────────────────────────────────────
# Public: candidate updates AI-profiling consent (F-02)
# ──────────────────────────────────────────────
@router.post("/track/{token}/ai-consent", status_code=204)
async def set_ai_profiling_consent(
    token: str,
    granted: bool = Form(...),
    service: ApplicationService = Depends(_get_service),
) -> None:
    """Allow the candidate to grant or revoke AI-profiling consent.

    Authenticated only by knowledge of their tracking ``token`` — same surface
    as ``GET /track/{token}``. Revoking does NOT delete past LLM results
    (those are out of our control in Anthropic's history), but it stops all
    future LLM calls for this application.
    """
    await service.set_ai_profiling_consent(token, granted=granted)


# F-C1 (audit_api): mitigate email enumeration. This endpoint is public by
# design (the apply flow asks the candidate "you may already have applied to
# this job"), so we cannot fully lock it behind auth without breaking the UX.
# Instead we cap it to 5 requests per minute per IP — mass enumeration of
# emails becomes impractical (5 × 60 × 24 = 7200/day max per IP). A follow-up
# task should also redact the response payload to only `has_duplicates: bool`
# + `public_token`, removing email/phone/candidate_name (DuplicateCheckMatch).
@router.post(
    "/duplicate-check",
    response_model=DuplicateCheckResponse,
    dependencies=[Depends(rate_limit("5/minute"))],
)
async def duplicate_check(
    data: DuplicateCheckRequest,
    service: ApplicationService = Depends(_get_service),
) -> DuplicateCheckResponse:
    return await service.check_duplicate(data)


# ──────────────────────────────────────────────
# Public: candidate tracks own application
# ──────────────────────────────────────────────
# F-M6 / F-M8 (audit_api): per-IP rate-limit (10/min) to slow enumeration of
# tracking tokens, plus ``Cache-Control: no-store`` so shared proxies / CDNs
# never cache a per-candidate response keyed by a secret URL.
@router.get(
    "/track/{token}",
    response_model=ApplicationTrackingRead,
    dependencies=[Depends(rate_limit("10/minute"))],
)
async def track_application(
    token: str,
    response: Response,
    service: ApplicationService = Depends(_get_service),
) -> ApplicationTrackingRead:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return await service.track_application(token)


# ──────────────────────────────────────────────
# HR: list applications
# ──────────────────────────────────────────────
@router.get("", response_model=ApplicationList)
async def list_applications(
    company: CurrentCompany,
    _user: CurrentUser,
    job_id: uuid.UUID | None = Query(None),
    stage_id: uuid.UUID | None = Query(None),
    search: str | None = Query(None),
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
    company: CurrentCompany,
    _user: CurrentUser,
    service: ApplicationService = Depends(_get_service),
) -> ApplicationRead:
    return await service.get_application_detail(application_id, company.id)


@router.get("/{application_id}/cv-parse", response_model=CVParseJobRead | None)
async def get_cv_parse_status(
    application_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    service: ApplicationService = Depends(_get_service),
) -> CVParseJobRead | None:
    return await service.get_cv_parse_status(application_id, company.id)


@router.post("/{application_id}/cv-parse/retry", response_model=CVParseJobRead)
async def retry_cv_parse(
    request: Request,
    application_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    company: CurrentCompany,
    _user: CurrentUser,
    service: ApplicationService = Depends(_get_service),
) -> CVParseJobRead:
    return await service.retry_cv_parse(
        application_id, company.id, background_tasks, language=detect_language(request)
    )


# ──────────────────────────────────────────────
# HR: job matching results
# ──────────────────────────────────────────────
@router.get("/{application_id}/matches", response_model=list[CandidateJobMatchRead])
async def get_job_matches(
    application_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> list[CandidateJobMatchRead]:
    await ensure_application_in_company(db, application_id, company.id)
    repo = ApplicationRepository(db)
    matches = await repo.get_job_matches(application_id)
    return [CandidateJobMatchRead.model_validate(m) for m in matches]


# ──────────────────────────────────────────────
# HR: activity timeline
# ──────────────────────────────────────────────
@router.get("/{application_id}/events", response_model=list[ApplicationEventRead])
async def list_application_events(
    application_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    service: ApplicationService = Depends(_get_service),
) -> list[ApplicationEventRead]:
    return await service.list_events(application_id, company.id)


# ──────────────────────────────────────────────
# HR: score a candidate
# ──────────────────────────────────────────────
@router.post("/{application_id}/score", response_model=ScoreRead)
async def score_application(
    application_id: uuid.UUID,
    data: ScoreCreate,
    company: CurrentCompany,
    user: CurrentUser,
    service: ApplicationService = Depends(_get_service),
) -> ScoreRead:
    return await service.score_application(application_id, company.id, user.id, data)


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
