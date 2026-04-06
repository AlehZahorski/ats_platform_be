from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.reviews.models import (
    ReviewAssignment,
    ReviewResponse,
    ScorecardCriterion,
    ScorecardTemplate,
)
from app.modules.reviews.schemas import ReviewAssignmentCreate, ScorecardTemplateCreate


class ReviewsRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_templates(self, company_id: uuid.UUID) -> list[ScorecardTemplate]:
        result = await self.db.execute(
            select(ScorecardTemplate)
            .where(ScorecardTemplate.company_id == company_id)
            .options(selectinload(ScorecardTemplate.criteria))
            .order_by(ScorecardTemplate.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_template(self, template_id: uuid.UUID, company_id: uuid.UUID) -> ScorecardTemplate | None:
        result = await self.db.execute(
            select(ScorecardTemplate)
            .where(ScorecardTemplate.id == template_id, ScorecardTemplate.company_id == company_id)
            .options(selectinload(ScorecardTemplate.criteria))
        )
        return result.scalar_one_or_none()

    async def create_template(self, company_id: uuid.UUID, data: ScorecardTemplateCreate) -> ScorecardTemplate:
        template = ScorecardTemplate(
            company_id=company_id,
            name=data.name,
            description=data.description,
            is_active=True,
        )
        self.db.add(template)
        await self.db.flush()

        for criterion in data.criteria:
            self.db.add(
                ScorecardCriterion(
                    template_id=template.id,
                    label=criterion.label,
                    description=criterion.description,
                    order_index=criterion.order_index,
                    max_score=criterion.max_score,
                )
            )
        await self.db.flush()
        return await self.get_template(template.id, company_id)  # type: ignore[return-value]

    async def create_assignment(
        self,
        application_id: uuid.UUID,
        assigned_by: uuid.UUID,
        data: ReviewAssignmentCreate,
    ) -> ReviewAssignment:
        assignment = ReviewAssignment(
            application_id=application_id,
            reviewer_id=data.reviewer_id,
            assigned_by=assigned_by,
            template_id=data.template_id,
            due_at=data.due_at,
            status="pending",
        )
        self.db.add(assignment)
        await self.db.flush()
        return await self.get_assignment(assignment.id)  # type: ignore[return-value]

    async def list_assignments(self, application_id: uuid.UUID) -> list[ReviewAssignment]:
        result = await self.db.execute(
            select(ReviewAssignment)
            .where(ReviewAssignment.application_id == application_id)
            .options(
                selectinload(ReviewAssignment.reviewer),
                selectinload(ReviewAssignment.assigner),
                selectinload(ReviewAssignment.template).selectinload(ScorecardTemplate.criteria),
                selectinload(ReviewAssignment.responses),
            )
            .order_by(ReviewAssignment.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_assignment(self, assignment_id: uuid.UUID) -> ReviewAssignment | None:
        result = await self.db.execute(
            select(ReviewAssignment)
            .where(ReviewAssignment.id == assignment_id)
            .execution_options(populate_existing=True)
            .options(
                selectinload(ReviewAssignment.reviewer),
                selectinload(ReviewAssignment.assigner),
                selectinload(ReviewAssignment.template).selectinload(ScorecardTemplate.criteria),
                selectinload(ReviewAssignment.responses),
            )
        )
        return result.scalar_one_or_none()

    async def get_assignment_for_application_reviewer(
        self,
        application_id: uuid.UUID,
        reviewer_id: uuid.UUID,
    ) -> ReviewAssignment | None:
        result = await self.db.execute(
            select(ReviewAssignment).where(
                ReviewAssignment.application_id == application_id,
                ReviewAssignment.reviewer_id == reviewer_id,
            )
        )
        return result.scalar_one_or_none()

    async def replace_responses(
        self,
        assignment: ReviewAssignment,
        responses: list[dict[str, object]],
        *,
        overall_comment: str | None,
        recommendation: str | None,
    ) -> ReviewAssignment:
        existing = await self.db.execute(
            select(ReviewResponse).where(ReviewResponse.assignment_id == assignment.id)
        )
        for response in existing.scalars().all():
            await self.db.delete(response)

        for item in responses:
            self.db.add(
                ReviewResponse(
                    assignment_id=assignment.id,
                    criterion_id=item["criterion_id"],  # type: ignore[arg-type]
                    score=item["score"],  # type: ignore[arg-type]
                    comment=item.get("comment"),  # type: ignore[arg-type]
                )
            )

        assignment.status = "submitted"
        assignment.submitted_at = func.now()
        assignment.overall_comment = overall_comment
        assignment.recommendation = recommendation
        await self.db.flush()
        return await self.get_assignment(assignment.id)  # type: ignore[return-value]
