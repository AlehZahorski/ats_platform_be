"""Public, unauthenticated endpoints powering the /firmy section.

Three reads:
  • GET /companies/public             — paginated, filterable list of profiles
  • GET /companies/public/{slug}      — full profile by slug
  • GET /companies/public/{slug}/jobs — open jobs for one company

The endpoints never expose internal/auth fields. Anything not in the
response schemas (CompanyPublicSummary / CompanyPublicDetail) stays
server-side.

Lives in a separate router from the existing `companies/router.py` so
the singular `/company` prefix (owner self-management) doesn't collide
with the plural `/companies` prefix used here for the public listing.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.enums.jobs import JobStatus
from app.core.exceptions import NotFoundError
from app.modules.companies.models import Company
from app.modules.companies.schemas import (
    CompanyPublicDetail,
    CompanyPublicListResponse,
)
from app.modules.jobs.models import Job

router = APIRouter()


# ──────────────────────────────────────────────────────────────────────
# List
# ──────────────────────────────────────────────────────────────────────

# Maps the FilterSidebar "Wielkość firmy" buckets to integer ranges on
# companies.employee_count. Kept in the router because the contract is
# part of the public API surface — UI sends these tokens verbatim.
_SIZE_BUCKETS: dict[str, tuple[int | None, int | None]] = {
    "1-10": (1, 10),
    "11-50": (11, 50),
    "51-200": (51, 200),
    "201-500": (201, 500),
    "500+": (501, None),
}


@router.get("/public", response_model=CompanyPublicListResponse)
async def list_public_companies(
    q: str | None = Query(
        None, min_length=1, description="Free text — matched against company name and tagline."
    ),
    industry: list[str] | None = Query(
        None, description="One or more industry tokens (Fintech, SaaS, …)."
    ),
    size: list[str] | None = Query(
        None, description="Employee buckets: 1-10, 11-50, 51-200, 201-500, 500+."
    ),
    location: str | None = Query(None, description="Substring match on HQ location."),
    work_mode: list[str] | None = Query(
        None, description="remote / hybrid / office — derived from remote_percentage."
    ),
    verified_only: bool = Query(False),
    sort: str = Query("newest", pattern="^(newest|jobs|name)$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(24, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    # Subquery — open-jobs count per company. LEFT JOIN so companies with
    # zero open jobs still appear in the list.
    jobs_count = (
        select(Job.company_id, func.count(Job.id).label("open_jobs_count"))
        .where(Job.status == JobStatus.open)
        .group_by(Job.company_id)
        .subquery()
    )

    base = (
        select(Company, func.coalesce(jobs_count.c.open_jobs_count, 0).label("open_jobs_count"))
        .outerjoin(jobs_count, jobs_count.c.company_id == Company.id)
        # Don't list companies that haven't started a public profile yet
        # (slug NULL means owner never opened the public-profile editor).
        .where(Company.slug.is_not(None))
    )

    if q:
        term = f"%{q.strip()}%"
        base = base.where(Company.name.ilike(term) | Company.tagline.ilike(term))
    if industry:
        base = base.where(Company.industry.in_(industry))
    if location:
        base = base.where(Company.hq_location.ilike(f"%{location.strip()}%"))
    if verified_only:
        base = base.where(Company.is_verified.is_(True))

    if size:
        size_clauses = []
        for token in size:
            bucket = _SIZE_BUCKETS.get(token)
            if not bucket:
                continue
            low, high = bucket
            if high is None:
                size_clauses.append(Company.employee_count >= low)
            else:
                size_clauses.append(
                    (Company.employee_count >= low) & (Company.employee_count <= high)
                )
        if size_clauses:
            from sqlalchemy import or_

            base = base.where(or_(*size_clauses))

    if work_mode:
        # remote_percentage is the canonical signal. The FE filter UX shows
        # three options, mapped here:
        #   remote → >= 80%   hybrid → 20–79%   office → <= 19%
        from sqlalchemy import or_

        mode_clauses = []
        if "remote" in work_mode:
            mode_clauses.append(Company.remote_percentage >= 80)
        if "hybrid" in work_mode:
            mode_clauses.append(
                (Company.remote_percentage >= 20) & (Company.remote_percentage < 80)
            )
        if "office" in work_mode:
            mode_clauses.append(
                (Company.remote_percentage.is_(None)) | (Company.remote_percentage < 20)
            )
        if mode_clauses:
            base = base.where(or_(*mode_clauses))

    # Sort
    if sort == "jobs":
        base = base.order_by(
            func.coalesce(jobs_count.c.open_jobs_count, 0).desc(), Company.created_at.desc()
        )
    elif sort == "name":
        base = base.order_by(Company.name.asc())
    else:  # newest
        base = base.order_by(Company.created_at.desc())

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.execute(base.offset(skip).limit(limit))).all()

    items = [_summary(company, open_jobs_count) for company, open_jobs_count in rows]
    return {"items": items, "total": total}


# ──────────────────────────────────────────────────────────────────────
# Detail
# ──────────────────────────────────────────────────────────────────────


@router.get("/public/{slug}", response_model=CompanyPublicDetail)
async def get_public_company(slug: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    jobs_count = (
        select(func.count(Job.id))
        .where(Job.status == JobStatus.open, Job.company_id == Company.id)
        .correlate(Company)
        .scalar_subquery()
    )

    row = (
        await db.execute(
            select(Company, jobs_count.label("open_jobs_count")).where(Company.slug == slug)
        )
    ).first()
    if not row:
        raise NotFoundError("Firma nie została znaleziona.")

    company, open_jobs_count = row
    return _detail(company, open_jobs_count)


# ──────────────────────────────────────────────────────────────────────
# Jobs of one company
# ──────────────────────────────────────────────────────────────────────


@router.get("/public/{slug}/jobs")
async def list_public_company_jobs(
    slug: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Open jobs for a given company. Powers the 'Aktualne oferty pracy'
    section on the profile page. Mirrors the slim shape of /jobs/public."""
    company = (await db.execute(select(Company).where(Company.slug == slug))).scalar_one_or_none()
    if not company:
        raise NotFoundError("Firma nie została znaleziona.")

    base = (
        select(Job)
        .where(Job.company_id == company.id, Job.status == JobStatus.open)
        .order_by(Job.created_at.desc())
        .options(selectinload(Job.company))
    )

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    jobs = (await db.execute(base.offset(skip).limit(limit))).scalars().all()

    return {
        "items": [
            {
                "id": str(j.id),
                "title": j.title,
                "slug": j.slug,
                "location": j.location,
                "work_mode": j.work_mode,
                "contract_type": j.contract_type,
                "seniority": j.seniority,
                "employment_size": j.employment_size,
                "salary_min": j.salary_min,
                "salary_max": j.salary_max,
                "salary_currency": j.salary_currency,
                "salary_period": j.salary_period,
                "tech_stack": j.tech_stack,
                "created_at": j.created_at.isoformat(),
            }
            for j in jobs
        ],
        "total": total,
    }


# ──────────────────────────────────────────────────────────────────────
# Response shaping helpers
# ──────────────────────────────────────────────────────────────────────


def _summary(company: Company, open_jobs_count: int) -> dict[str, Any]:
    return {
        "id": company.id,
        "slug": company.slug,
        "name": company.name,
        "is_verified": company.is_verified,
        "logo_url": company.logo_url,
        "banner_url": company.banner_url,
        "tagline": company.tagline,
        "industry": company.industry,
        "employee_count": company.employee_count,
        "hq_location": company.hq_location,
        "founded_year": company.founded_year,
        "remote_percentage": company.remote_percentage,
        "tech_stack": company.tech_stack or [],
        "open_jobs_count": int(open_jobs_count or 0),
    }


def _detail(company: Company, open_jobs_count: int) -> dict[str, Any]:
    return {
        **_summary(company, open_jobs_count),
        "description": company.description,
        "website": company.website,
        "how_we_work": company.how_we_work or [],
        "benefits": company.benefits or [],
        "recruitment_process": company.recruitment_process or [],
        "timeline": company.timeline or [],
        "faq": company.faq or [],
        "gallery": company.gallery or [],
    }
