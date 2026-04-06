from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentCompany, CurrentUser, RecruiterOrOwner
from app.modules.reviews.schemas import (
    ReviewAssignmentCreate,
    ReviewAssignmentRead,
    ReviewAssignmentSubmit,
    ReviewSummaryRead,
    ScorecardTemplateCreate,
    ScorecardTemplateRead,
)
from app.modules.reviews.service import ReviewsService

router = APIRouter()


def _svc(db: AsyncSession = Depends(get_db)) -> ReviewsService:
    return ReviewsService(db)


@router.get("/templates", response_model=list[ScorecardTemplateRead])
async def list_templates(
    company: CurrentCompany,
    _user: CurrentUser,
    svc: ReviewsService = Depends(_svc),
) -> list[ScorecardTemplateRead]:
    templates = await svc.list_templates(company.id)
    return [ScorecardTemplateRead.model_validate(item) for item in templates]


@router.post("/templates", response_model=ScorecardTemplateRead, status_code=status.HTTP_201_CREATED)
async def create_template(
    data: ScorecardTemplateCreate,
    company: CurrentCompany,
    _user: RecruiterOrOwner,
    svc: ReviewsService = Depends(_svc),
) -> ScorecardTemplateRead:
    template = await svc.create_template(company.id, data)
    return ScorecardTemplateRead.model_validate(template)


@router.get("/applications/{application_id}/assignments", response_model=list[ReviewAssignmentRead])
async def list_assignments(
    application_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    svc: ReviewsService = Depends(_svc),
) -> list[ReviewAssignmentRead]:
    assignments = await svc.list_assignments(application_id, company.id)
    return [ReviewAssignmentRead.model_validate(item) for item in assignments]


@router.get("/applications/{application_id}/summary", response_model=ReviewSummaryRead)
async def get_summary(
    application_id: uuid.UUID,
    company: CurrentCompany,
    _user: CurrentUser,
    svc: ReviewsService = Depends(_svc),
) -> ReviewSummaryRead:
    return await svc.get_summary(application_id, company.id)


@router.post("/applications/{application_id}/assignments", response_model=ReviewAssignmentRead, status_code=status.HTTP_201_CREATED)
async def create_assignment(
    application_id: uuid.UUID,
    data: ReviewAssignmentCreate,
    company: CurrentCompany,
    user: RecruiterOrOwner,
    svc: ReviewsService = Depends(_svc),
) -> ReviewAssignmentRead:
    assignment = await svc.create_assignment(
        application_id=application_id,
        company_id=company.id,
        assigned_by=user.id,
        data=data,
    )
    return ReviewAssignmentRead.model_validate(assignment)


@router.post("/assignments/{assignment_id}/submit", response_model=ReviewAssignmentRead)
async def submit_assignment(
    assignment_id: uuid.UUID,
    data: ReviewAssignmentSubmit,
    company: CurrentCompany,
    user: CurrentUser,
    svc: ReviewsService = Depends(_svc),
) -> ReviewAssignmentRead:
    assignment = await svc.submit_assignment(
        assignment_id=assignment_id,
        current_user_id=user.id,
        company_id=company.id,
        data=data,
    )
    return ReviewAssignmentRead.model_validate(assignment)
