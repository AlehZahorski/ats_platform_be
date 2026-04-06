from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ScorecardCriterionCreate(BaseModel):
    label: str
    description: str | None = None
    order_index: int = 0
    max_score: int = Field(default=5, ge=1, le=10)


class ScorecardTemplateCreate(BaseModel):
    name: str
    description: str | None = None
    criteria: list[ScorecardCriterionCreate]


class ScorecardCriterionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str
    description: str | None
    order_index: int
    max_score: int


class ScorecardTemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    description: str | None
    is_active: bool
    criteria: list[ScorecardCriterionRead] = []
    created_at: datetime


class ReviewAssignmentCreate(BaseModel):
    reviewer_id: uuid.UUID
    template_id: uuid.UUID
    due_at: datetime | None = None


class ReviewAssignmentResponseInput(BaseModel):
    criterion_id: uuid.UUID
    score: int = Field(ge=1, le=10)
    comment: str | None = None


class ReviewAssignmentSubmit(BaseModel):
    responses: list[ReviewAssignmentResponseInput]
    overall_comment: str | None = None
    recommendation: str | None = None


class ReviewerUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: str


class ReviewResponseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    criterion_id: uuid.UUID
    score: int
    comment: str | None


class ReviewAssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    reviewer_id: uuid.UUID
    assigned_by: uuid.UUID | None
    template_id: uuid.UUID
    status: str
    due_at: datetime | None
    submitted_at: datetime | None
    overall_comment: str | None
    recommendation: str | None
    reviewer: ReviewerUserRead | None = None
    assigner: ReviewerUserRead | None = None
    template: ScorecardTemplateRead
    responses: list[ReviewResponseRead] = []
    created_at: datetime


class ReviewSummaryRead(BaseModel):
    total_assignments: int
    pending_count: int
    submitted_count: int
    average_score: float | None = None
