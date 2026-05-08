from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class AnswerInput(BaseModel):
    field_id: uuid.UUID
    value: Any


class ApplicationCreate(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    phone: str | None = None
    answers: list[AnswerInput] = []


class AnswerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    field_id: uuid.UUID
    field_label: str | None = None
    field_type: str | None = None
    value: Any


class StageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    order_index: int


class ScoreRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    application_id: uuid.UUID
    recruiter_id: uuid.UUID | None
    communication: int | None
    technical: int | None
    culture_fit: int | None
    created_at: datetime


class StageHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    stage: StageRead
    changed_at: datetime
    changed_by: uuid.UUID | None


class ApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    job_id: uuid.UUID
    first_name: str
    last_name: str
    email: str
    phone: str | None
    cv_url: str | None
    stage_id: uuid.UUID | None
    stage: StageRead | None
    public_token: str
    created_at: datetime
    answers: list[AnswerRead] = []
    scores: list[ScoreRead] = []
    stage_history: list[StageHistoryRead] = []
    candidate_profile: "CandidateProfileRead | None" = None
    latest_cv_parse_job: "CVParseJobRead | None" = None


class DuplicateCheckRequest(BaseModel):
    job_id: uuid.UUID
    email: EmailStr
    phone: str | None = None


class DuplicateCheckMatch(BaseModel):
    application_id: uuid.UUID
    job_id: uuid.UUID
    candidate_name: str
    email: str
    phone: str | None
    stage_name: str | None = None
    job_title: str | None = None
    public_token: str
    created_at: datetime
    match_reasons: list[str] = []


class DuplicateCheckResponse(BaseModel):
    has_duplicates: bool
    confidence: str = "none"
    matches: list[DuplicateCheckMatch] = []


class ApplicationListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    job_id: uuid.UUID
    first_name: str
    last_name: str
    email: str
    cv_url: str | None
    stage: StageRead | None
    created_at: datetime


class ApplicationList(BaseModel):
    items: list[ApplicationListItem]
    total: int


class ScoreCreate(BaseModel):
    communication: int = Field(ge=1, le=5)
    technical: int = Field(ge=1, le=5)
    culture_fit: int = Field(ge=1, le=5)


# Public tracking response
class TrackingStageHistory(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    stage: StageRead
    changed_at: datetime


class TrackingJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    department: str | None
    location: str | None


class ApplicationTrackingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    first_name: str
    last_name: str
    stage: StageRead | None
    stage_history: list[TrackingStageHistory] = []
    created_at: datetime
    job: TrackingJobRead | None = None


# ─── Bulk Operations ──────────────────────────────────────────────────────────
from typing import Literal

class BulkAction(BaseModel):
    application_ids: list[uuid.UUID]
    action: Literal["stage_change", "reject", "tag"]
    payload: dict[str, Any] = {}
    # stage_change: {"stage_id": "uuid"}
    # reject:       {}
    # tag:          {"tag_id": "uuid"}

class BulkResult(BaseModel):
    updated: int
    failed: int
    action: str


class ParsedSkillRead(BaseModel):
    name: str


class ParsedExperienceRead(BaseModel):
    title: str | None = None
    company: str | None = None
    date_range: str | None = None
    description: str | None = None


class ParsedEducationRead(BaseModel):
    school: str | None = None
    degree: str | None = None
    date_range: str | None = None
    description: str | None = None


class CandidateProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    headline: str | None
    summary: str | None
    skills: list[ParsedSkillRead] = []
    experience: list[ParsedExperienceRead] = []
    education: list[ParsedEducationRead] = []
    parsing_status: str
    parsing_error: str | None
    last_parsed_at: datetime | None


class CVParseJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    cv_url: str | None
    status: str
    error_message: str | None
    raw_result: dict[str, Any] | None = None
    normalized_result: dict[str, Any] | None = None
    parser_version: str
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CVParseConfirmPayload(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    phone: str | None = None
    headline: str | None = None
    summary: str | None = None
    skills: list[ParsedSkillRead] = []
    experience: list[ParsedExperienceRead] = []
    education: list[ParsedEducationRead] = []
