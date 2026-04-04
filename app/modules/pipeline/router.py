
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import CurrentCompany, CurrentUser, RecruiterOrOwner
from app.modules.applications.models import Application
from app.modules.audit.service import AuditService
from app.modules.pipeline.repository import PipelineRepository
from app.modules.pipeline.schemas import (
    StageCreate,
    StageHistoryRead,
    StageRead,
    StageReorderRequest,
    StageUpdate,
    UpdateStageRequest,
)
from app.services.candidate_notifications import send_stage_change_notification

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


@router.post("", response_model=StageRead, status_code=status.HTTP_201_CREATED)
async def create_stage(
    data: StageCreate,
    _user: RecruiterOrOwner,
    repo: PipelineRepository = Depends(_repo),
    db: AsyncSession = Depends(get_db),
) -> StageRead:
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Stage name is required")
    stage = await repo.create_stage(name)
    await db.commit()
    return StageRead.model_validate(stage)


@router.patch("/{stage_id}", response_model=StageRead)
async def rename_stage(
    stage_id: uuid.UUID,
    data: StageUpdate,
    _user: RecruiterOrOwner,
    repo: PipelineRepository = Depends(_repo),
    db: AsyncSession = Depends(get_db),
) -> StageRead:
    stage = await repo.get_stage(stage_id)
    if not stage:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stage not found")

    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Stage name is required")

    stage = await repo.update_stage_name(stage, name)
    await db.commit()
    return StageRead.model_validate(stage)


@router.post("/reorder", response_model=list[StageRead])
async def reorder_stages(
    data: StageReorderRequest,
    _user: RecruiterOrOwner,
    repo: PipelineRepository = Depends(_repo),
    db: AsyncSession = Depends(get_db),
) -> list[StageRead]:
    existing_ids = {stage.id for stage in await repo.list_stages()}
    requested_ids = {item.id for item in data.stages}
    if existing_ids != requested_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="All stages must be included in reorder request")

    reordered = await repo.reorder_stages([(item.id, item.order_index) for item in data.stages])
    await db.commit()
    return [StageRead.model_validate(stage) for stage in reordered]


@router.delete("/{stage_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_stage(
    stage_id: uuid.UUID,
    _user: RecruiterOrOwner,
    repo: PipelineRepository = Depends(_repo),
    db: AsyncSession = Depends(get_db),
) -> None:
    stage = await repo.get_stage(stage_id)
    if not stage:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stage not found")

    applications_count, history_count = await repo.stage_usage_counts(stage_id)
    if applications_count > 0 or history_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Stage cannot be deleted because it is already used by candidates or stage history",
        )

    await repo.delete_stage(stage)
    await db.commit()


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
        await send_stage_change_notification(
            db=db,
            background_tasks=background_tasks,
            company_id=company.id,
            stage_id=stage.id,
            candidate_email=application.email,
            candidate_name=f"{application.first_name} {application.last_name}",
            job_title=job.title if job else "position",
            stage_name=stage.name,
            tracking_url=tracking_url,
            company_name=company.name,
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
