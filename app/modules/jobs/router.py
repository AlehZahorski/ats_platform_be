import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.dependencies import CurrentCompany, CurrentUser
from app.modules.jobs.repository import JobRepository
from app.modules.jobs.schemas import AssignTemplateRequest, JobCreate, JobList, JobRead, JobUpdate
from app.modules.jobs.service import JobService
from app.modules.forms.schemas import FormTemplateRead

router = APIRouter()


def _repo(db: AsyncSession = Depends(get_db)) -> JobRepository:
    return JobRepository(db)


def _serialize_job(job) -> JobRead:
    return JobService.serialize(job)


@router.get("/public")
async def list_public_jobs(
    q: str | None = Query(None, min_length=1),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Public endpoint returning open jobs for the candidate job board."""
    from app.modules.jobs.models import Job

    stmt = select(Job).where(Job.status == "open").order_by(Job.created_at.desc()).offset(skip).limit(limit)
    count_stmt = select(Job).where(Job.status == "open")

    if q:
        term = f"%{q.strip()}%"
        search_filter = (
            Job.title.ilike(term)
            | Job.department.ilike(term)
            | Job.location.ilike(term)
            | Job.remote_constraints.ilike(term)
        )
        stmt = stmt.where(search_filter)
        count_stmt = count_stmt.where(search_filter)

    items = (await db.execute(stmt)).scalars().all()
    total = len((await db.execute(count_stmt)).scalars().all())

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
    """Public endpoint — returns job info + form template fields for the apply page."""
    from app.modules.jobs.models import Job, JobFormTemplate
    from app.modules.forms.models import FormTemplate
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(Job)
        .where(Job.id == job_id, Job.status == "open")
        .options(
            selectinload(Job.form_template_link).selectinload(JobFormTemplate.template).selectinload(FormTemplate.fields)
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or not accepting applications")

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
    repo: JobRepository = Depends(_repo),
) -> JobRead:
    job = await JobService(repo).create(company.id, data)
    return _serialize_job(job)


@router.get("", response_model=JobList)
async def list_jobs(
    company: CurrentCompany,
    _user: CurrentUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    job_status: Optional[str] = Query(None, alias="status"),
    repo: JobRepository = Depends(_repo),
) -> JobList:
    jobs, total = await repo.list(company.id, skip=skip, limit=limit, status=job_status)
    return JobList(items=[_serialize_job(j) for j in jobs], total=total)


@router.get("/{job_id}", response_model=JobRead)
async def get_job(
    job_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    repo: JobRepository = Depends(_repo),
) -> JobRead:
    job = await repo.get_by_id(job_id, company.id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _serialize_job(job)


@router.patch("/{job_id}", response_model=JobRead)
async def update_job(
    job_id: uuid.UUID,
    data: JobUpdate,
    company: CurrentCompany,
    _user: CurrentUser,
    repo: JobRepository = Depends(_repo),
) -> JobRead:
    job = await repo.get_by_id(job_id, company.id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    updated = await JobService(repo).update(job, data)
    return _serialize_job(updated)


@router.put("/{job_id}/template", response_model=JobRead)
async def assign_template(
    job_id: uuid.UUID,
    data: AssignTemplateRequest,
    company: CurrentCompany,
    _user: CurrentUser,
    repo: JobRepository = Depends(_repo),
) -> JobRead:
    job = await repo.get_by_id(job_id, company.id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    await repo.assign_template(job_id, data.template_id)
    updated = await repo.get_by_id(job_id, company.id)
    return _serialize_job(updated)


@router.delete("/{job_id}")
async def delete_job(
    job_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    repo: JobRepository = Depends(_repo),
) -> Response:
    job = await repo.get_by_id(job_id, company.id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    await repo.delete(job)
    return Response(status_code=204)
