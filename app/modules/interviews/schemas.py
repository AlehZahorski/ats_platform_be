from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.enums.interviews import InterviewStatus


class InterviewCreate(BaseModel):
    scheduled_at: datetime
    duration_minutes: int | None = 60
    meeting_url: str | None = None
    notes: str | None = None
    recruiter_id: uuid.UUID | None = None
    status: InterviewStatus = InterviewStatus.scheduled


class InterviewUpdate(BaseModel):
    scheduled_at: datetime | None = None
    duration_minutes: int | None = None
    meeting_url: str | None = None
    notes: str | None = None
    recruiter_id: uuid.UUID | None = None
    status: InterviewStatus | None = None


class RecruiterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str


class InterviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    recruiter_id: uuid.UUID | None
    scheduled_at: datetime
    duration_minutes: int | None
    meeting_url: str | None
    notes: str | None
    status: InterviewStatus
    recruiter: RecruiterRead | None
    created_at: datetime
    updated_at: datetime
