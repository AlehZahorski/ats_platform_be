from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentCompany, CurrentUser
from app.modules.applications.models import Application
from app.modules.pipeline.models import ApplicationStageHistory, PipelineStage
from app.modules.jobs.models import Job
from app.modules.reports.schemas import (
    ApplicationsOverTimeReport,
    JobApplicationsReport,
    JobApplicationsRow,
    OverviewReport,
    PipelineReport,
    PipelineStageReport,
    SourceReport,
    SourcesReport,
    TimeSeriesPoint,
    TimeToHireReport,
)

router = APIRouter()


def _date_from_days(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


async def _hired_stage(db: AsyncSession) -> PipelineStage | None:
    """The terminal 'hired' stage, matched case-insensitively by name."""
    result = await db.execute(
        select(PipelineStage).where(func.lower(PipelineStage.name) == "hired")
    )
    return result.scalar_one_or_none()


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
        select(PipelineStage).where(func.lower(PipelineStage.name) == "hired")
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
            Job.company_id == company.id,
            Application.created_at >= since,
            ApplicationStageHistory.stage_id == stage.id,
        )
    )
    rows = result.all()

    if not rows:
        return TimeToHireReport(avg_days=0, min_days=0, max_days=0, total_hired=0)

    durations = [
        (row.changed_at - row.created_at.replace(tzinfo=UTC)).days
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
        .where(Job.company_id == company.id, Application.created_at >= since)
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
        .where(Job.company_id == company.id, Application.created_at >= since)
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


@router.get("/overview", response_model=OverviewReport)
async def overview_report(
    company: CurrentCompany,
    _user: CurrentUser,
    days: int = Query(30, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
) -> OverviewReport:
    """Top-level KPIs: applications, hires, hire rate, avg time-to-hire, active jobs."""
    since = _date_from_days(days)

    total_applications = (
        await db.execute(
            select(func.count(Application.id))
            .join(Application.job)
            .where(Job.company_id == company.id, Application.created_at >= since)
        )
    ).scalar_one() or 0

    active_jobs = (
        await db.execute(
            select(func.count(Job.id)).where(
                Job.company_id == company.id, Job.status == "open"
            )
        )
    ).scalar_one() or 0

    # Hires + time-to-hire, derived from the stage-history rows for "hired".
    total_hired = 0
    avg_tth = 0.0
    stage = await _hired_stage(db)
    if stage:
        rows = (
            await db.execute(
                select(Application.created_at, ApplicationStageHistory.changed_at)
                .join(
                    ApplicationStageHistory,
                    ApplicationStageHistory.application_id == Application.id,
                )
                .join(Application.job)
                .where(
                    Job.company_id == company.id,
                    Application.created_at >= since,
                    ApplicationStageHistory.stage_id == stage.id,
                )
            )
        ).all()
        durations = [
            (r.changed_at - r.created_at.replace(tzinfo=UTC)).days
            for r in rows
            if r.changed_at and r.created_at
        ]
        total_hired = len(durations)
        if durations:
            avg_tth = round(sum(durations) / len(durations), 1)

    hire_rate = round((total_hired / total_applications) * 100, 1) if total_applications else 0.0

    return OverviewReport(
        total_applications=total_applications,
        total_hired=total_hired,
        hire_rate=hire_rate,
        avg_time_to_hire_days=avg_tth,
        active_jobs=active_jobs,
    )


@router.get("/applications-over-time", response_model=ApplicationsOverTimeReport)
async def applications_over_time(
    company: CurrentCompany,
    _user: CurrentUser,
    days: int = Query(30, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
) -> ApplicationsOverTimeReport:
    """Daily application counts, zero-filled for every day in the window so the
    chart has a continuous x-axis."""
    since = _date_from_days(days)
    day_col = func.date(Application.created_at)

    result = await db.execute(
        select(day_col.label("day"), func.count(Application.id).label("count"))
        .join(Application.job)
        .where(Job.company_id == company.id, Application.created_at >= since)
        .group_by(day_col)
        .order_by(day_col)
    )
    counts: dict[str, int] = {str(r.day): r.count for r in result.all()}

    # Zero-fill the full range (inclusive of today).
    start = (datetime.now(UTC) - timedelta(days=days - 1)).date()
    points: list[TimeSeriesPoint] = []
    total = 0
    for i in range(days):
        d = (start + timedelta(days=i)).isoformat()
        c = counts.get(d, 0)
        total += c
        points.append(TimeSeriesPoint(date=d, count=c))

    return ApplicationsOverTimeReport(points=points, total=total)


@router.get("/by-job", response_model=JobApplicationsReport)
async def applications_by_job(
    company: CurrentCompany,
    _user: CurrentUser,
    days: int = Query(30, ge=7, le=365),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> JobApplicationsReport:
    """Which jobs attract the most applications (top N in the window)."""
    since = _date_from_days(days)

    result = await db.execute(
        select(
            Job.id,
            Job.title,
            func.count(Application.id).label("count"),
        )
        .join(Application, Application.job_id == Job.id)
        .where(Job.company_id == company.id, Application.created_at >= since)
        .group_by(Job.id, Job.title)
        .order_by(func.count(Application.id).desc())
        .limit(limit)
    )
    rows = result.all()
    total = sum(r.count for r in rows) or 1

    return JobApplicationsReport(
        total=total,
        jobs=[
            JobApplicationsRow(
                job_id=str(r.id),
                job_title=r.title,
                count=r.count,
                percentage=round((r.count / total) * 100, 1),
            )
            for r in rows
        ],
    )
