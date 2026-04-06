from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.applications.models import Application
from app.modules.jobs.models import Job
from app.modules.reviews.models import ReviewResponse, ScorecardCriterion
from app.modules.reviews.repository import ReviewsRepository
from app.modules.reviews.schemas import (
    ReviewAssignmentCreate,
    ReviewAssignmentRead,
    ReviewAssignmentSubmit,
    ReviewSummaryRead,
    ScorecardTemplateCreate,
)
from app.modules.users.models import User


DEFAULT_TEMPLATE = ScorecardTemplateCreate(
    name="Default Hiring Manager Scorecard",
    description="Standard scorecard for hiring manager feedback",
    criteria=[
        {"label": "Role Fit", "description": "How well the candidate matches the role", "order_index": 0, "max_score": 5},
        {"label": "Technical Strength", "description": "Relevant skills and experience", "order_index": 1, "max_score": 5},
        {"label": "Team Collaboration", "description": "Communication and collaboration potential", "order_index": 2, "max_score": 5},
    ],
)


class ReviewsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = ReviewsRepository(db)

    async def list_templates(self, company_id: uuid.UUID):
        templates = await self.repo.list_templates(company_id)
        if templates:
            return templates
        await self.repo.create_template(company_id, DEFAULT_TEMPLATE)
        return await self.repo.list_templates(company_id)

    async def create_template(self, company_id: uuid.UUID, data: ScorecardTemplateCreate):
        if not data.criteria:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Scorecard template requires at least one criterion")
        return await self.repo.create_template(company_id, data)

    async def create_assignment(
        self,
        *,
        application_id: uuid.UUID,
        company_id: uuid.UUID,
        assigned_by: uuid.UUID,
        data: ReviewAssignmentCreate,
    ):
        await self._ensure_application_in_company(application_id, company_id)
        reviewer = await self._get_reviewer(data.reviewer_id, company_id)
        template = await self.repo.get_template(data.template_id, company_id)
        if not template:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scorecard template not found")
        existing = await self.repo.get_assignment_for_application_reviewer(application_id, reviewer.id)
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This reviewer is already assigned to the candidate")
        return await self.repo.create_assignment(application_id, assigned_by, data)

    async def list_assignments(self, application_id: uuid.UUID, company_id: uuid.UUID):
        await self._ensure_application_in_company(application_id, company_id)
        return await self.repo.list_assignments(application_id)

    async def submit_assignment(
        self,
        *,
        assignment_id: uuid.UUID,
        current_user_id: uuid.UUID,
        company_id: uuid.UUID,
        data: ReviewAssignmentSubmit,
    ):
        assignment = await self.repo.get_assignment(assignment_id)
        if not assignment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review assignment not found")
        await self._ensure_application_in_company(assignment.application_id, company_id)
        if assignment.reviewer_id != current_user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the assigned reviewer can submit this scorecard")

        criteria_ids = {criterion.id: criterion for criterion in assignment.template.criteria}
        if len(data.responses) != len(criteria_ids):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Every scorecard criterion must be reviewed")

        seen: set[uuid.UUID] = set()
        payload: list[dict[str, object]] = []
        for response in data.responses:
            criterion = criteria_ids.get(response.criterion_id)
            if not criterion:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid scorecard criterion")
            if response.criterion_id in seen:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Duplicate scorecard criterion response")
            if response.score > criterion.max_score:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Score for '{criterion.label}' cannot exceed {criterion.max_score}",
                )
            seen.add(response.criterion_id)
            payload.append(response.model_dump())

        return await self.repo.replace_responses(
            assignment,
            payload,
            overall_comment=data.overall_comment,
            recommendation=data.recommendation,
        )

    async def get_summary(self, application_id: uuid.UUID, company_id: uuid.UUID) -> ReviewSummaryRead:
        await self._ensure_application_in_company(application_id, company_id)
        assignments = await self.repo.list_assignments(application_id)
        total = len(assignments)
        pending = len([item for item in assignments if item.status != "submitted"])
        submitted = total - pending

        result = await self.db.execute(
            select(func.avg(ReviewResponse.score))
            .join_from(ReviewResponse, ReviewResponse.assignment)
            .where(ReviewResponse.assignment.has(application_id=application_id))
        )
        average = result.scalar_one_or_none()
        return ReviewSummaryRead(
            total_assignments=total,
            pending_count=pending,
            submitted_count=submitted,
            average_score=float(average) if average is not None else None,
        )

    async def _ensure_application_in_company(self, application_id: uuid.UUID, company_id: uuid.UUID) -> None:
        result = await self.db.execute(
            select(Application)
            .join(Job, Application.job_id == Job.id)
            .where(Application.id == application_id, Job.company_id == company_id)
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    async def _get_reviewer(self, reviewer_id: uuid.UUID, company_id: uuid.UUID) -> User:
        result = await self.db.execute(
            select(User).where(
                User.id == reviewer_id,
                User.company_id == company_id,
                User.role == "manager",
            )
        )
        reviewer = result.scalar_one_or_none()
        if not reviewer:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hiring manager not found")
        return reviewer
