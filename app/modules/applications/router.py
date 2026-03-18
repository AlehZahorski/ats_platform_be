import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import select, update
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
    BulkAction,
    BulkResult,
    ScoreCreate,
    ScoreRead,
)
from app.modules.application_events.models import ApplicationEvent
from app.modules.audit.models import AuditLog
from app.modules.jobs.models import Job
from app.modules.pipeline.models import ApplicationStageHistory
from app.modules.pipeline.repository import PipelineRepository
from app.modules.tags.repository import TagRepository
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
    result = ApplicationTrackingRead.model_validate(application)
    if hasattr(application, "job") and application.job:
        from app.modules.applications.schemas import TrackingJobRead
        result.job = TrackingJobRead.model_validate(application.job)
    return result


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

# ──────────────────────────────────────────────
# HR: bulk operations
# ──────────────────────────────────────────────
@router.post("/bulk", response_model=BulkResult)
async def bulk_action(
    data: BulkAction,
    company: CurrentCompany,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> BulkResult:
    from app.modules.applications.models import Application

    updated = 0
    failed = 0

    for app_id in data.application_ids:
        try:
            # Verify app belongs to company
            result = await db.execute(
                select(Application)
                .join(Job, Application.job_id == Job.id)
                .where(Application.id == app_id, Job.company_id == company.id)
            )
            app = result.scalar_one_or_none()
            if not app:
                failed += 1
                continue

            if data.action == "stage_change":
                stage_id = uuid.UUID(data.payload["stage_id"])
                app.stage_id = stage_id
                history = ApplicationStageHistory(
                    application_id=app_id,
                    stage_id=stage_id,
                    changed_by=user.id,
                )
                db.add(history)

            elif data.action == "reject":
                # Find rejected stage
                from app.modules.pipeline.models import PipelineStage
                from sqlalchemy import func as sqlfunc
                res = await db.execute(
                    select(PipelineStage).where(sqlfunc.lower(PipelineStage.name) == "rejected")
                )
                rejected_stage = res.scalar_one_or_none()
                if rejected_stage:
                    app.stage_id = rejected_stage.id
                    history = ApplicationStageHistory(
                        application_id=app_id,
                        stage_id=rejected_stage.id,
                        changed_by=user.id,
                    )
                    db.add(history)

            elif data.action == "tag":
                tag_id = uuid.UUID(data.payload["tag_id"])
                from app.modules.tags.models import ApplicationTag
                existing = await db.execute(
                    select(ApplicationTag).where(
                        ApplicationTag.application_id == app_id,
                        ApplicationTag.tag_id == tag_id,
                    )
                )
                if not existing.scalar_one_or_none():
                    db.add(ApplicationTag(application_id=app_id, tag_id=tag_id))

            # Log event
            db.add(ApplicationEvent(
                application_id=app_id,
                company_id=company.id,
                event_type="bulk_action",
                event_value=data.action,
                metadata_={"payload": data.payload, "user_id": str(user.id)},
            ))
            updated += 1

        except Exception:
            failed += 1
            continue

    # Audit log
    db.add(AuditLog(
        company_id=company.id,
        user_id=user.id,
        action="bulk_action",
        entity_type="application",
        metadata_={"action": data.action, "count": updated, "ids": [str(i) for i in data.application_ids]},
    ))

    await db.commit()
    return BulkResult(updated=updated, failed=failed, action=data.action)