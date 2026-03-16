import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.dependencies import CurrentCompany, CurrentUser
from app.modules.jobs.repository import JobRepository
from app.modules.jobs.schemas import AssignTemplateRequest, JobCreate, JobList, JobRead, JobUpdate
from app.modules.forms.schemas import FormTemplateRead

router = APIRouter()


def _repo(db: AsyncSession = Depends(get_db)) -> JobRepository:
    return JobRepository(db)


def _serialize_job(job) -> JobRead:
    data = JobRead.model_validate(job)
    if job.form_template_link:
        data.template_id = job.form_template_link.template_id
    return data


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
        "template": template,
    }


@router.post("", response_model=JobRead, status_code=201)
async def create_job(
    data: JobCreate,
    company: CurrentCompany,
    _user: CurrentUser,
    repo: JobRepository = Depends(_repo),
) -> JobRead:
    job = await repo.create(company.id, data)
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
    updated = await repo.update(job, data)
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