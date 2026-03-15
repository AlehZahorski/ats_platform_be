
import uuid

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentCompany, CurrentUser
from app.modules.jobs.repository import JobRepository
from app.modules.jobs.schemas import JobCreate, JobList, JobRead, JobUpdate

router = APIRouter()


def _repo(db: AsyncSession = Depends(get_db)) -> JobRepository:
    return JobRepository(db)


@router.post("", response_model=JobRead, status_code=201)
async def create_job(
    data: JobCreate,
    company: CurrentCompany,
    _user: CurrentUser,
    repo: JobRepository = Depends(_repo),
) -> JobRead:
    job = await repo.create(company.id, data)
    return JobRead.model_validate(job)


@router.get("", response_model=JobList)
async def list_jobs(
    company: CurrentCompany,
    _user: CurrentUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = Query(None),
    repo: JobRepository = Depends(_repo),
) -> JobList:
    jobs, total = await repo.list(company.id, skip=skip, limit=limit, status=status)
    return JobList(items=[JobRead.model_validate(j) for j in jobs], total=total)


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
    return JobRead.model_validate(job)


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
    return JobRead.model_validate(updated)


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
