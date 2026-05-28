from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.core.base_service import BaseService
from app.core.enums.reviews import ReviewStatus
from app.core.enums.users import UserRole
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, UnprocessableError
from app.core.i18n import t
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


def _default_template() -> ScorecardTemplateCreate:
    return ScorecardTemplateCreate(
        name="Default Hiring Manager Scorecard",
        description=t("reviews.default_scorecard_description"),
        criteria=[
            {"label": t("reviews.criterion.role_fit.label"), "description": t("reviews.criterion.role_fit.description"), "order_index": 0, "max_score": 5},
            {"label": t("reviews.criterion.technical_strength.label"), "description": t("reviews.criterion.technical_strength.description"), "order_index": 1, "max_score": 5},
            {"label": t("reviews.criterion.team_collaboration.label"), "description": t("reviews.criterion.team_collaboration.description"), "order_index": 2, "max_score": 5},
        ],
    )


class ReviewsService(BaseService[ReviewsRepository]):

    async def list_templates(self, company_id: uuid.UUID) -> list[ScorecardTemplate]:
        templates = await self.repository.list_templates(company_id)
        if templates:
            return templates
        await self.repository.create_template(company_id, _default_template())
        return await self.repository.list_templates(company_id)

    async def create_template(
        self, company_id: uuid.UUID, data: ScorecardTemplateCreate
    ) -> ScorecardTemplate:
        if not data.criteria:
            raise UnprocessableError(t("reviews.template_needs_criterion"))
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
            raise NotFoundError(t("reviews.template_not_found"))
        existing = await self.repository.get_assignment_for_application_reviewer(
            application_id, reviewer.id
        )
        if existing:
            raise ConflictError(t("reviews.reviewer_assigned"))
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
            raise NotFoundError(t("reviews.assignment_not_found"))
        await self._ensure_application_in_company(assignment.application_id, company_id)
        if assignment.reviewer_id != current_user_id:
            raise ForbiddenError(t("reviews.wrong_reviewer"))

        criteria_ids = {criterion.id: criterion for criterion in assignment.template.criteria}
        if len(data.responses) != len(criteria_ids):
            raise UnprocessableError(t("reviews.incomplete"))

        seen: set[uuid.UUID] = set()
        payload: list[dict[str, object]] = []
        for response in data.responses:
            criterion = criteria_ids.get(response.criterion_id)
            if not criterion:
                raise UnprocessableError(t("reviews.invalid_criterion"))
            if response.criterion_id in seen:
                raise UnprocessableError(t("reviews.duplicate_criterion"))
            if response.score > criterion.max_score:
                raise UnprocessableError(
                    t("reviews.score_exceeds_max", label=criterion.label, max_score=criterion.max_score)
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
            raise NotFoundError(t("reviews.application_not_found"))

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
            raise NotFoundError(t("reviews.hiring_manager_not_found"))
        return reviewer
