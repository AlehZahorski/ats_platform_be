from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.core.enums.jobs import ContractType, JobStatus, Seniority, SalaryPeriod, WorkMode


class JobOfferBase(BaseModel):
    title: str
    description: str | None = None
    department: str | None = None
    location: str | None = None
    role_summary: str | None = None
    role_purpose: str | None = None
    responsibilities: str | None = None
    must_haves: str | None = None
    nice_to_haves: str | None = None
    tech_stack: str | None = None
    domain_context: str | None = None
    seniority: Seniority | None = None
    experience_min_years: int | None = None
    experience_max_years: int | None = None
    work_mode: WorkMode | None = None
    remote_constraints: str | None = None
    success_profile: str | None = None
    team_context: str | None = None
    reporting_to: str | None = None
    value_proposition: str | None = None
    benefits: str | None = None
    hiring_process: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    salary_period: SalaryPeriod | None = None
    contract_type: ContractType | None = None


class JobCreate(JobOfferBase):
    status: JobStatus = JobStatus.draft
    template_id: uuid.UUID | None = None


class JobUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    department: str | None = None
    location: str | None = None
    role_summary: str | None = None
    role_purpose: str | None = None
    responsibilities: str | None = None
    must_haves: str | None = None
    nice_to_haves: str | None = None
    tech_stack: str | None = None
    domain_context: str | None = None
    seniority: Seniority | None = None
    experience_min_years: int | None = None
    experience_max_years: int | None = None
    work_mode: WorkMode | None = None
    remote_constraints: str | None = None
    success_profile: str | None = None
    team_context: str | None = None
    reporting_to: str | None = None
    value_proposition: str | None = None
    benefits: str | None = None
    hiring_process: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    salary_period: SalaryPeriod | None = None
    contract_type: ContractType | None = None
    status: JobStatus | None = None
    template_id: uuid.UUID | None = None


class AssignTemplateRequest(BaseModel):
    template_id: uuid.UUID | None = None


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    title: str
    description: str | None
    department: str | None
    location: str | None
    status: JobStatus
    role_summary: str | None
    role_purpose: str | None
    responsibilities: str | None
    must_haves: str | None
    nice_to_haves: str | None
    tech_stack: str | None
    domain_context: str | None
    seniority: Seniority | None
    experience_min_years: int | None
    experience_max_years: int | None
    work_mode: WorkMode | None
    remote_constraints: str | None
    success_profile: str | None
    team_context: str | None
    reporting_to: str | None
    value_proposition: str | None
    benefits: str | None
    hiring_process: str | None
    salary_min: int | None
    salary_max: int | None
    salary_currency: str | None
    salary_period: SalaryPeriod | None
    contract_type: ContractType | None
    created_at: datetime
    template_id: uuid.UUID | None = None
    publish_ready: bool = False
    publish_issues: list[str] = []
    analysis_score: int | None = None
    analysis_market_position: str | None = None
    analysis_summary: str | None = None
    analysis_strengths: list[str] = []
    analysis_improvements: list[str] = []

    @field_validator("analysis_strengths", "analysis_improvements", mode="before")
    @classmethod
    def none_to_empty_list(cls, v: object) -> object:
        return v if v is not None else []
    analysis_candidate_impact: str | None = None
    analysis_urgency_message: str | None = None
    analysis_at: datetime | None = None


class JobList(BaseModel):
    items: list[JobRead]
    total: int


class JobSuggestRead(BaseModel):
    role_summary: str | None = None
    role_purpose: str | None = None
    responsibilities: str | None = None
    must_haves: str | None = None
    nice_to_haves: str | None = None
    tech_stack: str | None = None
    team_context: str | None = None
    success_profile: str | None = None
    value_proposition: str | None = None
    benefits: str | None = None
    hiring_process: str | None = None


class JobOfferAnalysisRead(BaseModel):
    attractiveness_score: int
    market_position: str  # above_market | at_market | below_market
    summary: str
    strengths: list[str] = []
    improvements: list[str] = []
    candidate_impact: str
    urgency_message: str
