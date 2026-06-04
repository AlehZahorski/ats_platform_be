import uuid

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import CurrentCompany, CurrentUser, RecruiterOrOwner
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
from app.modules.pipeline.service import PipelineService
from app.services.candidate_notifications import send_stage_change_notification

router = APIRouter()


def _get_service(db: AsyncSession = Depends(get_db)) -> PipelineService:
    return PipelineService(PipelineRepository(db), AuditService(db), db)


@router.get("", response_model=list[StageRead])
async def list_stages(
    _user: CurrentUser,
    service: PipelineService = Depends(_get_service),
) -> list[StageRead]:
    stages = await service.repository.list_stages()
    return [StageRead.model_validate(s) for s in stages]


@router.post("", response_model=StageRead, status_code=201)
async def create_stage(
    data: StageCreate,
    _user: RecruiterOrOwner,
    service: PipelineService = Depends(_get_service),
) -> StageRead:
    stage = await service.create_stage(data.name)
    return StageRead.model_validate(stage)


@router.patch("/{stage_id}", response_model=StageRead)
async def rename_stage(
    stage_id: uuid.UUID,
    data: StageUpdate,
    _user: RecruiterOrOwner,
    service: PipelineService = Depends(_get_service),
) -> StageRead:
    stage = await service.rename_stage(stage_id, data.name)
    return StageRead.model_validate(stage)


@router.post("/reorder", response_model=list[StageRead])
async def reorder_stages(
    data: StageReorderRequest,
    _user: RecruiterOrOwner,
    service: PipelineService = Depends(_get_service),
) -> list[StageRead]:
    reordered = await service.reorder_stages([(item.id, item.order_index) for item in data.stages])
    return [StageRead.model_validate(s) for s in reordered]


@router.delete("/{stage_id}", status_code=204)
async def delete_stage(
    stage_id: uuid.UUID,
    _user: RecruiterOrOwner,
    service: PipelineService = Depends(_get_service),
) -> None:
    await service.delete_stage(stage_id)


@router.patch("/applications/{application_id}/stage", response_model=StageHistoryRead)
async def update_stage(
    application_id: uuid.UUID,
    data: UpdateStageRequest,
    background_tasks: BackgroundTasks,
    company: CurrentCompany,
    user: CurrentUser,
    service: PipelineService = Depends(_get_service),
) -> StageHistoryRead:
    ctx = await service.update_application_stage(
        application_id=application_id,
        stage_id=data.stage_id,
        company_id=company.id,
        user_id=user.id,
    )

    if data.notify_candidate:
        # Use the opaque public_token, never the guessable application_id
        # (the candidate-facing /track route only accepts the token).
        tracking_url = f"{settings.frontend_url}/track/{ctx.tracking_token}"
        await send_stage_change_notification(
            db=service.db,
            background_tasks=background_tasks,
            company_id=company.id,
            stage_id=data.stage_id,
            candidate_email=ctx.candidate_email,
            candidate_name=ctx.candidate_name,
            job_title=ctx.job_title,
            stage_name=ctx.stage_name,
            tracking_url=tracking_url,
            company_name=company.name,
            interview_at=ctx.interview.scheduled_at if ctx.interview else None,
            interview_url=ctx.interview.meeting_url if ctx.interview else None,
            interview_notes=ctx.interview.notes if ctx.interview else None,
            interview_duration_minutes=ctx.interview.duration_minutes if ctx.interview else None,
        )

    return StageHistoryRead.model_validate(ctx.history)


@router.get("/applications/{application_id}/history", response_model=list[StageHistoryRead])
async def get_stage_history(
    application_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    service: PipelineService = Depends(_get_service),
) -> list[StageHistoryRead]:
    history = await service.get_history(application_id, company.id)
    return [StageHistoryRead.model_validate(h) for h in history]
