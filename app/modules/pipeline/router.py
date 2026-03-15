
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import CurrentCompany, CurrentUser
from app.modules.applications.models import Application
from app.modules.audit.service import AuditService
from app.modules.pipeline.repository import PipelineRepository
from app.modules.pipeline.schemas import StageHistoryRead, StageRead, UpdateStageRequest
from app.services.mailer import mail_service

router = APIRouter()


def _repo(db: AsyncSession = Depends(get_db)) -> PipelineRepository:
    return PipelineRepository(db)


@router.get("", response_model=list[StageRead])
async def list_stages(
    _user: CurrentUser,
    repo: PipelineRepository = Depends(_repo),
) -> list[StageRead]:
    stages = await repo.list_stages()
    return [StageRead.model_validate(s) for s in stages]


@router.patch("/applications/{application_id}/stage", response_model=StageHistoryRead)
async def update_stage(
    application_id: uuid.UUID,
    data: UpdateStageRequest,
    background_tasks: BackgroundTasks,
    company: CurrentCompany,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    repo: PipelineRepository = Depends(_repo),
) -> StageHistoryRead:
    # Verify application belongs to this company
    from app.modules.jobs.models import Job
    result = await db.execute(
        select(Application)
        .join(Job, Application.job_id == Job.id)
        .where(Application.id == application_id, Job.company_id == company.id)
    )
    application = result.scalar_one_or_none()
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    stage = await repo.get_stage(data.stage_id)
    if not stage:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stage not found")

    # Update stage on application
    application.stage_id = stage.id
    await db.flush()

    # Record history
    history = await repo.record_stage_change(application_id, stage.id, user.id)

    # Audit log
    audit = AuditService(db)
    await audit.log(
        company_id=company.id,
        user_id=user.id,
        action="candidate_moved_stage",
        entity_type="application",
        entity_id=application_id,
        metadata={"stage_name": stage.name},
    )

    # Optional candidate notification
    if data.notify_candidate:
        tracking_url = f"{settings.frontend_url}/track/{application.public_token}"
        from app.modules.jobs.models import Job as JobModel
        job_result = await db.execute(select(JobModel).where(JobModel.id == application.job_id))
        job = job_result.scalar_one_or_none()
        mail_service.send_status_change(
            background_tasks,
            to_email=application.email,
            candidate_name=f"{application.first_name} {application.last_name}",
            job_title=job.title if job else "position",
            new_stage=stage.name,
            tracking_url=tracking_url,
        )

    return StageHistoryRead.model_validate(history)


@router.get("/applications/{application_id}/history", response_model=list[StageHistoryRead])
async def get_stage_history(
    application_id: uuid.UUID,
    _company: CurrentCompany,
    _user: CurrentUser,
    repo: PipelineRepository = Depends(_repo),
) -> list[StageHistoryRead]:
    history = await repo.get_history(application_id)
    return [StageHistoryRead.model_validate(h) for h in history]
