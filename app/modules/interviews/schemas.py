from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.core.enums.interviews import InterviewStatus


class InterviewCreate(BaseModel):
    scheduled_at: datetime
    duration_minutes: Optional[int] = 60
    meeting_url: Optional[str] = None
    notes: Optional[str] = None
    recruiter_id: Optional[uuid.UUID] = None
    status: InterviewStatus = InterviewStatus.scheduled


class InterviewUpdate(BaseModel):
    scheduled_at: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    meeting_url: Optional[str] = None
    notes: Optional[str] = None
    recruiter_id: Optional[uuid.UUID] = None
    status: Optional[InterviewStatus] = None


class RecruiterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str


class InterviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    recruiter_id: Optional[uuid.UUID]
    scheduled_at: datetime
    duration_minutes: Optional[int]
    meeting_url: Optional[str]
    notes: Optional[str]
    status: InterviewStatus
    recruiter: Optional[RecruiterRead]
    created_at: datetime
    updated_at: datetime
