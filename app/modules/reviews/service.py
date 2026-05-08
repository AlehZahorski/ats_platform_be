from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.core.base_service import BaseService
from app.core.enums.reviews import ReviewStatus
from app.core.enums.users import UserRole
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, UnprocessableError
from app.modules.reviews.models import ReviewResponse, ScorecardTemplate
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


class ReviewsService(BaseService[ReviewsRepository]):

    async def list_templates(self, company_id: uuid.UUID) -> list[ScorecardTemplate]:
        templates = await self.repository.list_templates(company_id)
        if templates:
            return templates
        await self.repository.create_template(company_id, DEFAULT_TEMPLATE)
        return await self.repository.list_templates(company_id)

    async def create_template(
        self, company_id: uuid.UUID, data: ScorecardTemplateCreate
    ) -> ScorecardTemplate:
        if not data.criteria:
            raise UnprocessableError("Scorecard template requires at least one criterion.")
        return await self.repository.create_template(company_id, data)

    async def create_assignment(
        self,
        *,
        application_id: uuid.UUID,
        company_id: uuid.UUID,
        assigned_by: uuid.UUID,
        data: ReviewAssignmentCreate,
    ) -> ReviewAssignmentRead:
        await self._ensure_application_in_company(application_id, company_id)
        reviewer = await self._get_reviewer(data.reviewer_id, company_id)
        template = await self.repository.get_template(data.template_id, company_id)
        if not template:
            raise NotFoundError("Scorecard template not found.")
        existing = await self.repository.get_assignment_for_application_reviewer(
            application_id, reviewer.id
        )
        if existing:
            raise ConflictError("This reviewer is already assigned to the candidate.")
        return await self.repository.create_assignment(application_id, assigned_by, data)

    async def list_assignments(
        self, application_id: uuid.UUID, company_id: uuid.UUID
    ) -> list[ReviewAssignmentRead]:
        await self._ensure_application_in_company(application_id, company_id)
        return await self.repository.list_assignments(application_id)

    async def submit_assignment(
        self,
        *,
        assignment_id: uuid.UUID,
        current_user_id: uuid.UUID,
        company_id: uuid.UUID,
        data: ReviewAssignmentSubmit,
    ) -> ReviewAssignmentRead:
        assignment = await self.repository.get_assignment(assignment_id)
        if not assignment:
            raise NotFoundError("Review assignment not found.")
        await self._ensure_application_in_company(assignment.application_id, company_id)
        if assignment.reviewer_id != current_user_id:
            raise ForbiddenError("Only the assigned reviewer can submit this scorecard.")

        criteria_ids = {criterion.id: criterion for criterion in assignment.template.criteria}
        if len(data.responses) != len(criteria_ids):
            raise UnprocessableError("Every scorecard criterion must be reviewed.")

        seen: set[uuid.UUID] = set()
        payload: list[dict[str, object]] = []
        for response in data.responses:
            criterion = criteria_ids.get(response.criterion_id)
            if not criterion:
                raise UnprocessableError("Invalid scorecard criterion.")
            if response.criterion_id in seen:
                raise UnprocessableError("Duplicate scorecard criterion response.")
            if response.score > criterion.max_score:
                raise UnprocessableError(
                    f"Score for '{criterion.label}' cannot exceed {criterion.max_score}."
                )
            seen.add(response.criterion_id)
            payload.append(response.model_dump())

        return await self.repository.replace_responses(
            assignment,
            payload,
            overall_comment=data.overall_comment,
            recommendation=data.recommendation,
        )

    async def get_summary(
        self, application_id: uuid.UUID, company_id: uuid.UUID
    ) -> ReviewSummaryRead:
        await self._ensure_application_in_company(application_id, company_id)
        assignments = await self.repository.list_assignments(application_id)
        total = len(assignments)
        pending = sum(1 for a in assignments if a.status != ReviewStatus.submitted)
        submitted = total - pending

        db = self.repository.db
        result = await db.execute(
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

    async def _ensure_application_in_company(
        self, application_id: uuid.UUID, company_id: uuid.UUID
    ) -> None:
        from app.modules.applications.models import Application
        from app.modules.jobs.models import Job

        db = self.repository.db
        result = await db.execute(
            select(Application)
            .join(Job, Application.job_id == Job.id)
            .where(Application.id == application_id, Job.company_id == company_id)
        )
        if not result.scalar_one_or_none():
            raise NotFoundError("Application not found.")

    async def _get_reviewer(self, reviewer_id: uuid.UUID, company_id: uuid.UUID) -> User:
        db = self.repository.db
        result = await db.execute(
            select(User).where(
                User.id == reviewer_id,
                User.company_id == company_id,
                User.role == UserRole.manager,
            )
        )
        reviewer = result.scalar_one_or_none()
        if not reviewer:
            raise NotFoundError("Hiring manager not found.")
        return reviewer
