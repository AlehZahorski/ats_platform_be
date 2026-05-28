from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.enums.applications import BulkActionType, CVParseStatus, ParsingStatus


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
    candidate_profile: CandidateProfileRead | None = None
    latest_cv_parse_job: CVParseJobRead | None = None


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
    # M7 (audit_backend_code) verification: `application_id` is intentionally
    # NOT a body field — the value comes from the URL path only, so there is
    # no URL/body mismatch to validate. Do not add it here without changing
    # `POST /applications/{application_id}/score`.
    communication: int = Field(ge=1, le=5)
    technical: int = Field(ge=1, le=5)
    culture_fit: int = Field(ge=1, le=5)


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


class BulkAction(BaseModel):
    application_ids: list[uuid.UUID]
    action: BulkActionType
    payload: dict[str, Any] = {}


class BulkResult(BaseModel):
    updated: int
    failed: int
    action: BulkActionType


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


class PersonalitySignalsRead(BaseModel):
    team_player: bool | None = None
    team_player_reason: str | None = None
    leadership_indicators: str | None = None
    growth_mindset: str | None = None
    communication_style: str | None = None


class TechnicalSkillRead(BaseModel):
    name: str
    level: str | None = None


class LanguageRead(BaseModel):
    name: str
    level: str | None = None


class CertificationRead(BaseModel):
    name: str
    issuer: str | None = None
    year: int | None = None


class CandidateProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    parser_version: str = "v1-regex"
    # v1 fields
    headline: str | None
    summary: str | None
    skills: list[ParsedSkillRead] = []
    experience: list[ParsedExperienceRead] = []
    education: list[ParsedEducationRead] = []
    parsing_status: ParsingStatus
    parsing_error: str | None
    last_parsed_at: datetime | None
    # v2 LLM enrichment fields
    personal_summary: str | None = None
    executive_summary: str | None = None
    location: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    technical_skills: list[TechnicalSkillRead] | None = None
    soft_skills: list[ParsedSkillRead] | None = None
    languages: list[LanguageRead] | None = None
    certifications: list[CertificationRead] | None = None
    hobbies: list[str] | None = None
    volunteering: list[str] | None = None
    total_experience_years: float | None = None
    seniority_estimate: str | None = None
    strengths: list[str] | None = None
    red_flags: list[str] | None = None
    personality_signals: PersonalitySignalsRead | None = None
    culture_fit_notes: str | None = None


class CVParseJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    cv_url: str | None
    status: CVParseStatus
    error_message: str | None
    raw_result: dict[str, Any] | None = None
    normalized_result: dict[str, Any] | None = None
    parser_version: str
    llm_model: str | None = None
    token_usage: dict[str, Any] | None = None
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
    # LLM enrichment fields — recruiter can edit before confirming
    personal_summary: str | None = None
    executive_summary: str | None = None
    location: str | None = None
    hobbies: list[str] | None = None
    seniority_estimate: str | None = None
    culture_fit_notes: str | None = None


class CandidateJobMatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    job_id: uuid.UUID
    match_score: int | None
    fit_score: int | None
    reasoning: str | None
    strengths_match: list[str] | None = None
    gaps: list[str] | None = None
    recommendation: str | None
    # F-08 (audit_ai_ethics): completed | llm_disabled | llm_failed | pending.
    # The UI uses this to distinguish "AI ran" from "AI never produced a result"
    # so failures don't silently look like a "not_a_match".
    match_status: str = "completed"
    llm_model: str | None = None
    created_at: datetime
