from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums.jobs import ContractType, JobStatus, Seniority, SalaryPeriod, WorkMode


# ── Shared literals ────────────────────────────────────────────────────────
RiskSeverity = Literal["low", "medium", "high"]
RiskLevel = Literal["low", "medium", "high"]


# ───────────────────────────────────────────────────────────────────────────
# Job offer — editable fields (shared between Create / Update)
# ───────────────────────────────────────────────────────────────────────────

class JobOfferFields(BaseModel):
    """All editable job offer fields. Title required only on Create."""
    title: str | None = None
    slug: str | None = None
    department: str | None = None
    location: str | None = None
    # Classification (multi-industry / multi-country support)
    category: str | None = None              # machine code from frontend categories config
    shift_system: str | None = None          # one_shift|two_shift|three_shift|weekend|equivalent
    employment_size: str | None = None       # full|part_50|part_75|temporary|internship|apprenticeship
    required_qualifications: list[str] | None = None
    # Role content
    role_summary: str | None = None
    role_purpose: str | None = None
    role_scope: str | None = None
    role_deliverables: str | None = None
    responsibilities: str | None = None
    must_haves: str | None = None
    nice_to_haves: str | None = None
    tech_stack: str | None = None
    domain_context: str | None = None
    # Experience & work conditions
    seniority: Seniority | None = None
    experience_min_years: int | None = None
    experience_max_years: int | None = None
    work_mode: WorkMode | None = None
    remote_constraints: str | None = None
    contract_type: ContractType | None = None
    # Culture & team
    success_profile: str | None = None
    team_context: str | None = None
    reporting_to: str | None = None
    value_proposition: str | None = None
    benefits: str | None = None
    hiring_process: str | None = None
    # Compensation
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    salary_period: SalaryPeriod | None = None


class JobCreate(JobOfferFields):
    title: str  # required on create — overrides optional base
    status: JobStatus = JobStatus.draft
    template_id: uuid.UUID | None = None


class JobUpdate(JobOfferFields):
    status: JobStatus | None = None
    template_id: uuid.UUID | None = None


class AssignTemplateRequest(BaseModel):
    template_id: uuid.UUID | None = None


class JobParseRequest(BaseModel):
    """Raw text from an existing job advertisement, to be structured via LLM."""
    text: str = Field(min_length=20, max_length=20000)


class JobParseResult(BaseModel):
    """Structured fields extracted from raw text. All fields optional — the
    parser returns whatever it could confidently extract.
    """
    title: str | None = None
    department: str | None = None
    location: str | None = None
    role_summary: str | None = None
    team_context: str | None = None
    value_proposition: str | None = None
    remote_constraints: str | None = None
    responsibilities: str | None = None
    must_haves: str | None = None
    nice_to_haves: str | None = None
    tech_stack: str | None = None
    benefits: str | None = None
    hiring_process: str | None = None
    work_mode: str | None = None
    contract_type: str | None = None
    seniority: str | None = None
    shift_system: str | None = None
    employment_size: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    salary_period: str | None = None
    experience_min_years: int | None = None
    experience_max_years: int | None = None


# ───────────────────────────────────────────────────────────────────────────
# AI-generated — analysis & risk assessment (persisted, 1:1 with Job)
# ───────────────────────────────────────────────────────────────────────────

class JobAnalysisRead(BaseModel):
    """Persisted attractiveness analysis."""
    model_config = ConfigDict(from_attributes=True)

    score: int | None = None
    market_position: str | None = None  # above_market | at_market | below_market
    summary: str | None = None
    strengths: list[str] = []
    improvements: list[str] = []
    candidate_impact: str | None = None
    urgency_message: str | None = None
    analyzed_at: datetime | None = None


class RiskFactor(BaseModel):
    name: str
    severity: RiskSeverity


class JobRiskAssessmentRead(BaseModel):
    """Persisted organizational risk assessment."""
    model_config = ConfigDict(from_attributes=True)

    score: int | None = None
    level: RiskLevel | None = None
    factors: list[RiskFactor] = []
    recommendations: list[str] = []
    assessed_at: datetime | None = None


# ───────────────────────────────────────────────────────────────────────────
# User-entered — risk items & mitigation actions (1:N with Job)
# ───────────────────────────────────────────────────────────────────────────

class RiskItemCreate(BaseModel):
    description: str
    severity: RiskSeverity = "medium"
    order: int = 0


class RiskItemUpdate(BaseModel):
    description: str | None = None
    severity: RiskSeverity | None = None
    order: int | None = None


class RiskItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    description: str
    severity: RiskSeverity
    order: int
    created_at: datetime


class MitigationActionCreate(BaseModel):
    description: str
    order: int = 0


class MitigationActionUpdate(BaseModel):
    description: str | None = None
    order: int | None = None


class MitigationActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    description: str
    order: int
    created_at: datetime


# ───────────────────────────────────────────────────────────────────────────
# Job — full response (nests analysis + risk + lists)
# ───────────────────────────────────────────────────────────────────────────

class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    title: str
    slug: str | None = None
    department: str | None
    location: str | None
    status: JobStatus

    # Classification
    category: str | None = None
    shift_system: str | None = None
    employment_size: str | None = None
    required_qualifications: list[str] = []

    # Role content
    role_summary: str | None
    role_purpose: str | None
    role_scope: str | None
    role_deliverables: str | None
    responsibilities: str | None
    must_haves: str | None
    nice_to_haves: str | None
    tech_stack: str | None
    domain_context: str | None

    # Experience & work conditions
    seniority: Seniority | None
    experience_min_years: int | None
    experience_max_years: int | None
    work_mode: WorkMode | None
    remote_constraints: str | None
    contract_type: ContractType | None

    # Compensation
    salary_min: int | None
    salary_max: int | None
    salary_currency: str | None
    salary_period: SalaryPeriod | None

    # Culture & team
    success_profile: str | None
    team_context: str | None
    reporting_to: str | None
    value_proposition: str | None
    benefits: str | None
    hiring_process: str | None

    # Meta
    created_at: datetime
    updated_at: datetime
    template_id: uuid.UUID | None = None
    publish_ready: bool = False
    publish_issues: list[str] = []
    suggest_used_at: datetime | None = None

    # Nested AI results + user-entered lists
    analysis: JobAnalysisRead | None = None
    risk_assessment: JobRiskAssessmentRead | None = None
    risk_items: list[RiskItemRead] = []
    mitigation_actions: list[MitigationActionRead] = []


class JobList(BaseModel):
    items: list[JobRead]
    total: int


# ───────────────────────────────────────────────────────────────────────────
# LLM suggest endpoint — returns generated content fields
# ───────────────────────────────────────────────────────────────────────────

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


# ───────────────────────────────────────────────────────────────────────────
# LLM analyze endpoint — legacy contract (different naming than JobAnalysisRead)
# Returned by POST /jobs/{id}/analyze; persisted form is JobAnalysisRead.
# ───────────────────────────────────────────────────────────────────────────

class JobOfferAnalysisRead(BaseModel):
    attractiveness_score: int
    market_position: str
    summary: str
    strengths: list[str] = []
    improvements: list[str] = []
    candidate_impact: str
    urgency_message: str
