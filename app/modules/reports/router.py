from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentCompany, CurrentUser
from app.modules.applications.models import Application
from app.modules.pipeline.models import ApplicationStageHistory, PipelineStage
from app.modules.reports.schemas import (
    PipelineReport,
    PipelineStageReport,
    SourceReport,
    SourcesReport,
    TimeToHireReport,
)

router = APIRouter()


def _date_from_days(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


@router.get("/time-to-hire", response_model=TimeToHireReport)
async def time_to_hire(
    company: CurrentCompany,
    _user: CurrentUser,
    days: int = Query(30, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
) -> TimeToHireReport:
    since = _date_from_days(days)

    # Find applications that reached "Hired" stage
    hired_stage = await db.execute(
        select(PipelineStage).where(
            func.lower(PipelineStage.name) == "hired"
        )
    )
    stage = hired_stage.scalar_one_or_none()

    if not stage:
        return TimeToHireReport(avg_days=0, min_days=0, max_days=0, total_hired=0)

    result = await db.execute(
        select(
            Application.created_at,
            ApplicationStageHistory.changed_at,
        )
        .join(
            ApplicationStageHistory,
            ApplicationStageHistory.application_id == Application.id,
        )
        .join(Application.job)
        .where(
            Application.created_at >= since,
            ApplicationStageHistory.stage_id == stage.id,
        )
    )
    rows = result.all()

    if not rows:
        return TimeToHireReport(avg_days=0, min_days=0, max_days=0, total_hired=0)

    durations = [
        (row.changed_at - row.created_at.replace(tzinfo=timezone.utc)).days
        for row in rows
        if row.changed_at and row.created_at
    ]

    if not durations:
        return TimeToHireReport(avg_days=0, min_days=0, max_days=0, total_hired=0)

    return TimeToHireReport(
        avg_days=round(sum(durations) / len(durations), 1),
        min_days=float(min(durations)),
        max_days=float(max(durations)),
        total_hired=len(durations),
    )


@router.get("/pipeline", response_model=PipelineReport)
async def pipeline_report(
    company: CurrentCompany,
    _user: CurrentUser,
    days: int = Query(30, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
) -> PipelineReport:
    since = _date_from_days(days)

    result = await db.execute(
        select(PipelineStage.name, func.count(Application.id).label("count"))
        .join(Application, Application.stage_id == PipelineStage.id)
        .join(Application.job)
        .where(Application.created_at >= since)
        .group_by(PipelineStage.name, PipelineStage.order_index)
        .order_by(PipelineStage.order_index)
    )
    rows = result.all()
    total = sum(r.count for r in rows) or 1

    return PipelineReport(
        total=total,
        stages=[
            PipelineStageReport(
                stage_name=r.name,
                count=r.count,
                percentage=round((r.count / total) * 100, 1),
            )
            for r in rows
        ],
    )


@router.get("/sources", response_model=SourcesReport)
async def sources_report(
    company: CurrentCompany,
    _user: CurrentUser,
    days: int = Query(30, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
) -> SourcesReport:
    since = _date_from_days(days)

    result = await db.execute(
        select(
            func.coalesce(Application.source, "direct").label("source"),
            func.count(Application.id).label("count"),
        )
        .join(Application.job)
        .where(Application.created_at >= since)
        .group_by(func.coalesce(Application.source, "direct"))
        .order_by(func.count(Application.id).desc())
    )
    rows = result.all()
    total = sum(r.count for r in rows) or 1

    return SourcesReport(
        total=total,
        sources=[
            SourceReport(
                source=r.source,
                count=r.count,
                percentage=round((r.count / total) * 100, 1),
            )
            for r in rows
        ],
    )