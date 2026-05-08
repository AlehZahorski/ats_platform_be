from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums.jobs import ContractType, JobStatus, Seniority, SalaryPeriod, WorkMode


class JobOfferBase(BaseModel):
    title: str
    description: str | None = None
    department: str | None = None
    location: str | None = None
    role_summary: str | None = None
    role_purpose: str | None = None
    responsibilities: list[str] = Field(default_factory=list)
    must_haves: list[str] = Field(default_factory=list)
    nice_to_haves: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    domain_context: str | None = None
    seniority: Seniority | None = None
    experience_min_years: int | None = Field(default=None, ge=0, le=50)
    experience_max_years: int | None = Field(default=None, ge=0, le=50)
    work_mode: WorkMode | None = None
    remote_constraints: str | None = None
    success_profile: str | None = None
    team_context: str | None = None
    reporting_to: str | None = None
    value_proposition: str | None = None
    benefits: list[str] = Field(default_factory=list)
    hiring_process: list[str] = Field(default_factory=list)
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
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
    responsibilities: list[str] | None = None
    must_haves: list[str] | None = None
    nice_to_haves: list[str] | None = None
    tech_stack: list[str] | None = None
    domain_context: str | None = None
    seniority: Seniority | None = None
    experience_min_years: int | None = Field(default=None, ge=0, le=50)
    experience_max_years: int | None = Field(default=None, ge=0, le=50)
    work_mode: WorkMode | None = None
    remote_constraints: str | None = None
    success_profile: str | None = None
    team_context: str | None = None
    reporting_to: str | None = None
    value_proposition: str | None = None
    benefits: list[str] | None = None
    hiring_process: list[str] | None = None
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
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
    responsibilities: list[str] = []
    must_haves: list[str] = []
    nice_to_haves: list[str] = []
    tech_stack: list[str] = []
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
    benefits: list[str] = []
    hiring_process: list[str] = []
    salary_min: int | None
    salary_max: int | None
    salary_currency: str | None
    salary_period: SalaryPeriod | None
    contract_type: ContractType | None
    created_at: datetime
    template_id: uuid.UUID | None = None
    publish_ready: bool = False
    publish_issues: list[str] = []


class JobList(BaseModel):
    items: list[JobRead]
    total: int
