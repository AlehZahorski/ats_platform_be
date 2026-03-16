import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import CurrentCompany, CurrentUser
from app.modules.applications.repository import ApplicationRepository
from app.modules.applications.schemas import (
    AnswerInput,
    AnswerRead,
    ApplicationCreate,
    ApplicationList,
    ApplicationListItem,
    ApplicationRead,
    ApplicationTrackingRead,
    ScoreCreate,
    ScoreRead,
)
from app.modules.jobs.models import Job
from app.modules.pipeline.repository import PipelineRepository
from app.services.file_storage import file_storage
from app.services.mailer import mail_service

router = APIRouter()


def _repo(db: AsyncSession = Depends(get_db)) -> ApplicationRepository:
    return ApplicationRepository(db)


# ──────────────────────────────────────────────
# Public: candidate submits application
# ──────────────────────────────────────────────
@router.post("/apply/{job_id}", status_code=201)
async def apply(
    request: Request,
    job_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    phone: Optional[str] = Form(None),
    answers: Optional[str] = Form(None),   # JSON string: [{field_id, value}]
    cv_file: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
) -> ApplicationRead:
    import json as _json

    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.status == "open")
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or not open")

    cv_url: Optional[str] = None
    if cv_file and cv_file.filename:
        cv_url = await file_storage.save_cv(cv_file)

    pipeline_repo = PipelineRepository(db)
    stages = await pipeline_repo.list_stages()
    initial_stage = stages[0] if stages else None

    # Parse dynamic answers
    parsed_answers = []
    if answers:
        try:
            raw = _json.loads(answers)
            parsed_answers = [
                AnswerInput(field_id=a["field_id"], value=a["value"])
                for a in raw if a.get("field_id") and a.get("value") not in (None, "")
            ]
        except Exception:
            pass

    app_repo = ApplicationRepository(db)
    data = ApplicationCreate(
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
        answers=parsed_answers,
    )
    application = await app_repo.create(
        job_id=job_id,
        data=data,
        cv_url=cv_url,
        initial_stage_id=initial_stage.id if initial_stage else None,
    )

    tracking_url = f"{settings.frontend_url}/track/{application.public_token}"
    mail_service.send_application_confirmation(
        background_tasks,
        to_email=email,
        candidate_name=f"{first_name} {last_name}",
        job_title=job.title,
        tracking_url=tracking_url,
    )

    return ApplicationRead.model_validate(application)


# ──────────────────────────────────────────────
# Public: candidate tracks own application
# ──────────────────────────────────────────────
@router.get("/track/{token}", response_model=ApplicationTrackingRead)
async def track_application(
    token: str,
    repo: ApplicationRepository = Depends(_repo),
) -> ApplicationTrackingRead:
    application = await repo.get_by_token(token)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    return ApplicationTrackingRead.model_validate(application)


# ──────────────────────────────────────────────
# HR: list applications (company-scoped)
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
    repo: ApplicationRepository = Depends(_repo),
) -> ApplicationList:
    apps, total = await repo.list(
        company_id=company.id,
        job_id=job_id,
        stage_id=stage_id,
        search=search,
        skip=skip,
        limit=limit,
    )
    return ApplicationList(
        items=[ApplicationListItem.model_validate(a) for a in apps],
        total=total,
    )


# ──────────────────────────────────────────────
# HR: single application detail
# ──────────────────────────────────────────────
@router.get("/{application_id}", response_model=ApplicationRead)
async def get_application(
    application_id: uuid.UUID,
    _company: CurrentCompany,
    _user: CurrentUser,
    repo: ApplicationRepository = Depends(_repo),
) -> ApplicationRead:
    application = await repo.get_by_id(application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    # Build response manually to populate field labels
    result = ApplicationRead.model_validate(application)
    result.answers = []
    for ans in (application.answers or []):
        answer = AnswerRead.model_validate(ans)
        if hasattr(ans, "field") and ans.field:
            answer.field_label = ans.field.label
            answer.field_type = ans.field.field_type
        result.answers.append(answer)
    return result


# ──────────────────────────────────────────────
# HR: score a candidate
# ──────────────────────────────────────────────
@router.post("/{application_id}/score", response_model=ScoreRead)
async def score_application(
    application_id: uuid.UUID,
    data: ScoreCreate,
    _company: CurrentCompany,
    user: CurrentUser,
    repo: ApplicationRepository = Depends(_repo),
) -> ScoreRead:
    application = await repo.get_by_id(application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    score = await repo.upsert_score(application_id, user.id, data)
    return ScoreRead.model_validate(score)