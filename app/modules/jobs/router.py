import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.dependencies import CurrentCompany, CurrentUser
from app.core.enums.jobs import JobStatus
from app.core.exceptions import NotFoundError
from app.modules.forms.schemas import FormTemplateRead
from app.modules.jobs.models import Job, JobFormTemplate
from app.modules.jobs.repository import JobRepository
from app.modules.jobs.schemas import AssignTemplateRequest, JobCreate, JobList, JobOfferAnalysisRead, JobRead, JobSuggestRead, JobUpdate
from app.modules.jobs.service import JobService
from app.core.i18n import detect_language

router = APIRouter()


def _get_service(db: AsyncSession = Depends(get_db)) -> JobService:
    return JobService(JobRepository(db))


@router.get("/public")
async def list_public_jobs(
    q: str | None = Query(None, min_length=1),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> dict:
    base = select(Job).where(Job.status == JobStatus.open)
    if q:
        term = f"%{q.strip()}%"
        search_filter = (
            Job.title.ilike(term)
            | Job.department.ilike(term)
            | Job.location.ilike(term)
            | Job.remote_constraints.ilike(term)
        )
        base = base.where(search_filter)

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    items = (await db.execute(base.order_by(Job.created_at.desc()).offset(skip).limit(limit))).scalars().all()

    return {
        "items": [
            {
                "id": str(job.id),
                "title": job.title,
                "department": job.department,
                "location": job.location,
                "description": job.description,
                "role_summary": job.role_summary,
                "work_mode": job.work_mode,
                "remote_constraints": job.remote_constraints,
                "contract_type": job.contract_type,
                "salary_min": job.salary_min,
                "salary_max": job.salary_max,
                "salary_currency": job.salary_currency,
                "salary_period": job.salary_period,
                "created_at": job.created_at.isoformat(),
            }
            for job in items
        ],
        "total": total,
    }


@router.get("/public/{job_id}")
async def get_public_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.modules.forms.models import FormTemplate

    result = await db.execute(
        select(Job)
        .where(Job.id == job_id, Job.status == JobStatus.open)
        .options(
            selectinload(Job.form_template_link)
            .selectinload(JobFormTemplate.template)
            .selectinload(FormTemplate.fields)
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise NotFoundError("Job not found or not accepting applications.")

    template = None
    if job.form_template_link and job.form_template_link.template:
        template = FormTemplateRead.model_validate(job.form_template_link.template)

    return {
        "id": str(job.id),
        "title": job.title,
        "department": job.department,
        "location": job.location,
        "description": job.description,
        "role_summary": job.role_summary,
        "role_purpose": job.role_purpose,
        "responsibilities": job.responsibilities,
        "must_haves": job.must_haves,
        "nice_to_haves": job.nice_to_haves,
        "tech_stack": job.tech_stack,
        "domain_context": job.domain_context,
        "seniority": job.seniority,
        "experience_min_years": job.experience_min_years,
        "experience_max_years": job.experience_max_years,
        "work_mode": job.work_mode,
        "remote_constraints": job.remote_constraints,
        "success_profile": job.success_profile,
        "team_context": job.team_context,
        "reporting_to": job.reporting_to,
        "value_proposition": job.value_proposition,
        "benefits": job.benefits,
        "hiring_process": job.hiring_process,
        "salary_min": job.salary_min,
        "salary_max": job.salary_max,
        "salary_currency": job.salary_currency,
        "salary_period": job.salary_period,
        "contract_type": job.contract_type,
        "template": template,
    }


@router.post("", response_model=JobRead, status_code=201)
async def create_job(
    data: JobCreate,
    company: CurrentCompany,
    _user: CurrentUser,
    service: JobService = Depends(_get_service),
) -> JobRead:
    job = await service.create(company.id, data)
    return JobService.serialize(job)


@router.get("", response_model=JobList)
async def list_jobs(
    company: CurrentCompany,
    _user: CurrentUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    job_status: Optional[JobStatus] = Query(None, alias="status"),
    service: JobService = Depends(_get_service),
) -> JobList:
    jobs, total = await service.repository.list_by_company(company.id, skip=skip, limit=limit, status=job_status)
    return JobList(items=[JobService.serialize(j) for j in jobs], total=total)


@router.get("/{job_id}", response_model=JobRead)
async def get_job(
    job_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    service: JobService = Depends(_get_service),
) -> JobRead:
    job = await service.repository.get_by_id_and_company(job_id, company.id)
    if not job:
        raise NotFoundError("Job not found.")
    return JobService.serialize(job)


@router.patch("/{job_id}", response_model=JobRead)
async def update_job(
    job_id: uuid.UUID,
    data: JobUpdate,
    company: CurrentCompany,
    _user: CurrentUser,
    service: JobService = Depends(_get_service),
) -> JobRead:
    job = await service.repository.get_by_id_and_company(job_id, company.id)
    if not job:
        raise NotFoundError("Job not found.")
    updated = await service.update(job, data)
    return JobService.serialize(updated)


@router.put("/{job_id}/template", response_model=JobRead)
async def assign_template(
    job_id: uuid.UUID,
    data: AssignTemplateRequest,
    company: CurrentCompany,
    _user: CurrentUser,
    service: JobService = Depends(_get_service),
) -> JobRead:
    job = await service.repository.get_by_id_and_company(job_id, company.id)
    if not job:
        raise NotFoundError("Job not found.")
    await service.repository.assign_template(job_id, data.template_id)
    updated = await service.repository.get_by_id_and_company(job_id, company.id)
    return JobService.serialize(updated)


@router.post("/{job_id}/analyze", response_model=JobOfferAnalysisRead)
async def analyze_job(
    request: Request,
    job_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    service: JobService = Depends(_get_service),
) -> JobOfferAnalysisRead:
    job = await service.repository.get_by_id_and_company(job_id, company.id)
    if not job:
        raise NotFoundError("Job not found.")
    return await service.analyze(job, language=detect_language(request))


@router.post("/{job_id}/suggest", response_model=JobSuggestRead)
async def suggest_job(
    request: Request,
    job_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    service: JobService = Depends(_get_service),
) -> JobSuggestRead:
    job = await service.repository.get_by_id_and_company(job_id, company.id)
    if not job:
        raise NotFoundError("Job not found.")
    return await service.suggest(job, language=detect_language(request))


@router.delete("/{job_id}", status_code=204)
async def delete_job(
    job_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    service: JobService = Depends(_get_service),
) -> Response:
    job = await service.repository.get_by_id_and_company(job_id, company.id)
    if not job:
        raise NotFoundError("Job not found.")
    await service.repository.delete(job)
    return Response(status_code=204)
