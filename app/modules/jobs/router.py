"""HTTP layer for the jobs module — thin, no business logic.

Each endpoint:
1. Resolves the entity (with company-scoped authorization)
2. Delegates to JobService for any logic
3. Returns the serialized response
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.dependencies import CurrentCompany, CurrentUser
from app.core.enums.jobs import JobStatus
from app.core.exceptions import NotFoundError
from app.core.i18n import detect_language, t
from app.modules.forms.schemas import FormTemplateRead
from app.modules.jobs.models import Job, JobFormTemplate, MitigationAction, RiskItem
from app.modules.jobs.repository import JobRepository
from app.modules.jobs.schemas import (
    AssignTemplateRequest,
    JobCreate,
    JobList,
    JobOfferAnalysisRead,
    JobParseRequest,
    JobParseResult,
    JobRead,
    JobRiskAssessmentRead,
    JobSuggestRead,
    JobUpdate,
    MitigationActionCreate,
    MitigationActionRead,
    MitigationActionUpdate,
    RiskItemCreate,
    RiskItemRead,
    RiskItemUpdate,
)
from app.modules.jobs.service import JobService

router = APIRouter()


# ───────────────────────────────────────────────────────────────────────────
# Dependency helpers
# ───────────────────────────────────────────────────────────────────────────

def _get_service(db: AsyncSession = Depends(get_db)) -> JobService:
    return JobService(JobRepository(db))


async def _get_owned_job(service: JobService, job_id: uuid.UUID, company_id: uuid.UUID) -> Job:
    job = await service.repository.get_by_id_and_company(job_id, company_id)
    if not job:
        raise NotFoundError(t("jobs.not_found"))
    return job


async def _get_owned_risk_item(service: JobService, job: Job, item_id: uuid.UUID) -> RiskItem:
    item = await service.risk_item_repo.get_by_id_and_job(item_id, job.id)
    if not item:
        raise NotFoundError(t("jobs.risk_item_not_found"))
    return item


async def _get_owned_mitigation(service: JobService, job: Job, action_id: uuid.UUID) -> MitigationAction:
    action = await service.mitigation_repo.get_by_id_and_job(action_id, job.id)
    if not action:
        raise NotFoundError(t("jobs.mitigation_not_found"))
    return action


# ───────────────────────────────────────────────────────────────────────────
# Public endpoints (unauthenticated)
# ───────────────────────────────────────────────────────────────────────────

@router.get("/public")
async def list_public_jobs(
    q: str | None = Query(None, min_length=1),
    category: list[str] | None = Query(None),
    work_mode: list[str] | None = Query(None),
    contract_type: list[str] | None = Query(None),
    seniority: list[str] | None = Query(None),
    employment_size: list[str] | None = Query(None),
    shift_system: list[str] | None = Query(None),
    qualification: list[str] | None = Query(None, description="Required qualification codes (e.g. forklift_udt). Job must list all selected."),
    job_ids: list[uuid.UUID] | None = Query(None, description="Whitelist of job IDs. Used by the 'Obserwowane' tab to fetch only saved jobs in one round-trip."),
    verified_only: bool = Query(False, description="Show only jobs from verified companies."),
    location: str | None = Query(None),
    salary_min: int | None = Query(None, ge=0),
    salary_max: int | None = Query(None, ge=0),
    sort: str = Query("newest", pattern="^(newest|salary_high|salary_low)$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.modules.companies.models import Company as CompanyModel

    base = select(Job).where(Job.status == JobStatus.open).options(selectinload(Job.company))

    # Whitelist filter — when present, all other filters still apply but
    # results are limited to the provided IDs. Empty list is treated as
    # "match nothing" so the saved-jobs tab safely degrades to empty state.
    if job_ids is not None:
        if not job_ids:
            return {"items": [], "total": 0}
        base = base.where(Job.id.in_(job_ids))

    if q:
        term = f"%{q.strip()}%"
        base = base.where(
            Job.title.ilike(term)
            | Job.department.ilike(term)
            | Job.role_summary.ilike(term)
            | Job.tech_stack.ilike(term)
        )
    if category:
        base = base.where(Job.category.in_(category))
    if work_mode:
        base = base.where(Job.work_mode.in_(work_mode))
    if contract_type:
        base = base.where(Job.contract_type.in_(contract_type))
    if seniority:
        base = base.where(Job.seniority.in_(seniority))
    if employment_size:
        base = base.where(Job.employment_size.in_(employment_size))
    if shift_system:
        base = base.where(Job.shift_system.in_(shift_system))
    if qualification:
        # Postgres ?| operator on JSONB: "any of these strings appears as a
        # top-level key OR as an array element". Our qualifications column is
        # a JSON array of strings, so this gives us OR semantics — a job
        # matches if it lists any of the requested quals.
        from sqlalchemy import text
        base = base.where(text("jobs.required_qualifications ?| :quals").bindparams(quals=qualification))
    if verified_only:
        base = base.join(CompanyModel, Job.company_id == CompanyModel.id).where(CompanyModel.is_verified.is_(True))
    if location:
        base = base.where(Job.location.ilike(f"%{location.strip()}%"))
    if salary_min is not None:
        # Job has either salary_max >= filter min, OR no max set
        base = base.where((Job.salary_max.is_(None)) | (Job.salary_max >= salary_min))
    if salary_max is not None:
        base = base.where((Job.salary_min.is_(None)) | (Job.salary_min <= salary_max))

    # Sorting
    if sort == "salary_high":
        base = base.order_by(Job.salary_max.desc().nullslast(), Job.created_at.desc())
    elif sort == "salary_low":
        base = base.order_by(Job.salary_min.asc().nullsfirst(), Job.created_at.desc())
    else:
        base = base.order_by(Job.created_at.desc())

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    items = (await db.execute(base.offset(skip).limit(limit))).scalars().all()

    return {"items": [_public_summary(j) for j in items], "total": total}


@router.get("/public/stats")
async def public_stats(db: AsyncSession = Depends(get_db)) -> dict:
    """Counters shown in the hero — total open jobs, total verified-or-active companies."""
    from app.modules.companies.models import Company

    total_jobs = (await db.execute(
        select(func.count()).select_from(select(Job).where(Job.status == JobStatus.open).subquery())
    )).scalar_one()
    # Count distinct companies with at least one open job — more honest than counting all companies
    total_companies = (await db.execute(
        select(func.count(func.distinct(Job.company_id))).where(Job.status == JobStatus.open)
    )).scalar_one()
    return {"total_jobs": total_jobs, "total_companies": total_companies}


@router.get("/public/popular")
async def public_popular(
    limit: int = Query(8, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Most-searched categories in the last 30 days.

    Falls back to most-common categories among open jobs when the search log
    is empty (cold-start — no search history yet).
    """
    from datetime import timedelta
    from app.modules.candidates.models import SearchLog

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    log_rows = (await db.execute(
        select(SearchLog.category, func.count().label("hits"))
        .where(SearchLog.category.is_not(None), SearchLog.created_at >= cutoff)
        .group_by(SearchLog.category)
        .order_by(func.count().desc())
        .limit(limit)
    )).all()

    if log_rows:
        return {"items": [{"category": row.category, "hits": row.hits} for row in log_rows]}

    # Cold start: top categories by open-job count.
    fallback_rows = (await db.execute(
        select(Job.category, func.count().label("hits"))
        .where(Job.status == JobStatus.open, Job.category.is_not(None))
        .group_by(Job.category)
        .order_by(func.count().desc())
        .limit(limit)
    )).all()
    return {"items": [{"category": row.category, "hits": row.hits} for row in fallback_rows]}


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
            .selectinload(FormTemplate.fields),
            selectinload(Job.company),
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise NotFoundError(t("jobs.not_accepting"))

    template = None
    if job.form_template_link and job.form_template_link.template:
        template = FormTemplateRead.model_validate(job.form_template_link.template)

    return {**_public_detail(job), "template": template}


# ───────────────────────────────────────────────────────────────────────────
# Authenticated CRUD
# ───────────────────────────────────────────────────────────────────────────

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
    jobs, total = await service.repository.list_by_company(
        company.id, skip=skip, limit=limit, status=job_status
    )
    return JobList(items=[JobService.serialize(j) for j in jobs], total=total)


@router.get("/{job_id}", response_model=JobRead)
async def get_job(
    job_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    service: JobService = Depends(_get_service),
) -> JobRead:
    job = await _get_owned_job(service, job_id, company.id)
    return JobService.serialize(job)


@router.patch("/{job_id}", response_model=JobRead)
async def update_job(
    job_id: uuid.UUID,
    data: JobUpdate,
    company: CurrentCompany,
    _user: CurrentUser,
    service: JobService = Depends(_get_service),
) -> JobRead:
    job = await _get_owned_job(service, job_id, company.id)
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
    job = await _get_owned_job(service, job_id, company.id)
    await service.repository.assign_template(job.id, data.template_id)
    refreshed = await service.repository.get_by_id_and_company(job.id, company.id)
    return JobService.serialize(refreshed)


@router.delete("/{job_id}", status_code=204)
async def delete_job(
    job_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    service: JobService = Depends(_get_service),
) -> Response:
    job = await _get_owned_job(service, job_id, company.id)
    await service.repository.delete(job)
    return Response(status_code=204)


@router.post("/parse", response_model=JobParseResult)
async def parse_existing_offer(
    data: JobParseRequest,
    request: Request,
    _company: CurrentCompany,
    _user: CurrentUser,
    service: JobService = Depends(_get_service),
) -> JobParseResult:
    """Extract structured fields from raw text of an existing job advertisement.

    This is NOT generation — it parses what's there. Used by the
    "Wklej istniejące ogłoszenie" import flow in the wizard.
    """
    extracted = await service.parse_text(data.text, language=detect_language(request))
    return JobParseResult(**{k: v for k, v in extracted.items() if k in JobParseResult.model_fields})


@router.post("/{job_id}/clone", response_model=JobRead, status_code=201)
async def clone_job(
    job_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    service: JobService = Depends(_get_service),
) -> JobRead:
    source = await _get_owned_job(service, job_id, company.id)
    cloned = await service.clone(source)
    return JobService.serialize(cloned)


# ───────────────────────────────────────────────────────────────────────────
# LLM endpoints
# ───────────────────────────────────────────────────────────────────────────

@router.post("/{job_id}/analyze", response_model=JobOfferAnalysisRead)
async def analyze_job(
    request: Request,
    job_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    service: JobService = Depends(_get_service),
) -> JobOfferAnalysisRead:
    job = await _get_owned_job(service, job_id, company.id)
    return await service.analyze(job, language=detect_language(request))


@router.post("/{job_id}/risk-analysis", response_model=JobRiskAssessmentRead)
async def assess_risk(
    request: Request,
    job_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    service: JobService = Depends(_get_service),
) -> JobRiskAssessmentRead:
    job = await _get_owned_job(service, job_id, company.id)
    return await service.assess_risk(job, language=detect_language(request))


@router.post("/{job_id}/suggest", response_model=JobSuggestRead)
async def suggest_job(
    request: Request,
    job_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    service: JobService = Depends(_get_service),
) -> JobSuggestRead:
    job = await _get_owned_job(service, job_id, company.id)
    return await service.suggest(job, language=detect_language(request))


# ───────────────────────────────────────────────────────────────────────────
# Risk items CRUD
# ───────────────────────────────────────────────────────────────────────────

@router.post("/{job_id}/risks", response_model=RiskItemRead, status_code=201)
async def add_risk_item(
    job_id: uuid.UUID,
    data: RiskItemCreate,
    company: CurrentCompany,
    _user: CurrentUser,
    service: JobService = Depends(_get_service),
) -> RiskItemRead:
    job = await _get_owned_job(service, job_id, company.id)
    item = await service.add_risk_item(job, data)
    return RiskItemRead.model_validate(item)


@router.patch("/{job_id}/risks/{risk_id}", response_model=RiskItemRead)
async def update_risk_item(
    job_id: uuid.UUID,
    risk_id: uuid.UUID,
    data: RiskItemUpdate,
    company: CurrentCompany,
    _user: CurrentUser,
    service: JobService = Depends(_get_service),
) -> RiskItemRead:
    job = await _get_owned_job(service, job_id, company.id)
    item = await _get_owned_risk_item(service, job, risk_id)
    updated = await service.update_risk_item(item, data)
    return RiskItemRead.model_validate(updated)


@router.delete("/{job_id}/risks/{risk_id}", status_code=204)
async def delete_risk_item(
    job_id: uuid.UUID,
    risk_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    service: JobService = Depends(_get_service),
) -> Response:
    job = await _get_owned_job(service, job_id, company.id)
    item = await _get_owned_risk_item(service, job, risk_id)
    await service.delete_risk_item(item)
    return Response(status_code=204)


# ───────────────────────────────────────────────────────────────────────────
# Mitigation actions CRUD
# ───────────────────────────────────────────────────────────────────────────

@router.post("/{job_id}/mitigations", response_model=MitigationActionRead, status_code=201)
async def add_mitigation(
    job_id: uuid.UUID,
    data: MitigationActionCreate,
    company: CurrentCompany,
    _user: CurrentUser,
    service: JobService = Depends(_get_service),
) -> MitigationActionRead:
    job = await _get_owned_job(service, job_id, company.id)
    action = await service.add_mitigation(job, data)
    return MitigationActionRead.model_validate(action)


@router.patch("/{job_id}/mitigations/{action_id}", response_model=MitigationActionRead)
async def update_mitigation(
    job_id: uuid.UUID,
    action_id: uuid.UUID,
    data: MitigationActionUpdate,
    company: CurrentCompany,
    _user: CurrentUser,
    service: JobService = Depends(_get_service),
) -> MitigationActionRead:
    job = await _get_owned_job(service, job_id, company.id)
    action = await _get_owned_mitigation(service, job, action_id)
    updated = await service.update_mitigation(action, data)
    return MitigationActionRead.model_validate(updated)


@router.delete("/{job_id}/mitigations/{action_id}", status_code=204)
async def delete_mitigation(
    job_id: uuid.UUID,
    action_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    service: JobService = Depends(_get_service),
) -> Response:
    job = await _get_owned_job(service, job_id, company.id)
    action = await _get_owned_mitigation(service, job, action_id)
    await service.delete_mitigation(action)
    return Response(status_code=204)


# ───────────────────────────────────────────────────────────────────────────
# Private — public response shaping (no leaking of internal/AI fields)
# ───────────────────────────────────────────────────────────────────────────

_PUBLIC_LIST_FIELDS: tuple[str, ...] = (
    "title", "slug", "department", "location", "role_summary",
    "work_mode", "remote_constraints", "contract_type",
    "salary_min", "salary_max", "salary_currency", "salary_period",
    "category", "shift_system", "employment_size", "required_qualifications",
    "seniority", "tech_stack",
)

_PUBLIC_DETAIL_FIELDS: tuple[str, ...] = (
    "title", "slug", "department", "location",
    "role_summary", "responsibilities", "must_haves",
    "nice_to_haves", "tech_stack", "domain_context",
    "seniority", "experience_min_years", "experience_max_years",
    "work_mode", "remote_constraints", "success_profile", "team_context",
    "reporting_to", "value_proposition", "benefits", "hiring_process",
    "salary_min", "salary_max", "salary_currency", "salary_period",
    "contract_type",
    "category", "shift_system", "employment_size", "required_qualifications",
    # Internal-only — never exposed on /public:
    #   role_purpose, role_scope, role_deliverables  (HR context)
    #   risk_items, mitigation_actions, analysis, risk_assessment  (AI / HR notes)
)


def _public_summary(job: Job) -> dict[str, Any]:
    return {
        "id": str(job.id),
        **{field: getattr(job, field) for field in _PUBLIC_LIST_FIELDS},
        "created_at": job.created_at.isoformat(),
        "company": _public_company(job.company) if getattr(job, "company", None) else None,
    }


def _public_detail(job: Job) -> dict[str, Any]:
    return {
        "id": str(job.id),
        **{field: getattr(job, field) for field in _PUBLIC_DETAIL_FIELDS},
        "company": _public_company(job.company) if getattr(job, "company", None) else None,
        "created_at": job.created_at.isoformat(),
    }


def _public_company(company) -> dict[str, Any]:
    """Slim public-safe representation of a company.
    NEVER expose internal fields. `is_verified` drives the green tick on cards;
    `slug` lets the FE link the company name on a job card to /firmy/{slug}.
    """
    return {
        "id":          str(company.id),
        "name":        company.name,
        "slug":        getattr(company, "slug", None),
        "logo_url":    getattr(company, "logo_url", None),
        "is_verified": getattr(company, "is_verified", False),
    }
