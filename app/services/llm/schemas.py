"""Pydantic schemas for LLM outputs (audit F-06).

Every Claude response is validated through one of these before it touches the
database or the API response. Halucynowane pole (`recommendation: "maybe"`)
albo brakujące pole = `LLMValidationError`, a caller decyduje czy fallback
do v1-regex / 422 / retry.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Shared error
# ---------------------------------------------------------------------------


class LLMValidationError(ValueError):
    """Raised when Claude's JSON does not match the expected shape."""


# ---------------------------------------------------------------------------
# CV enrichment (F-16: personality_signals → quoted evidence only)
# ---------------------------------------------------------------------------


class SkillItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    level: str | None = None


class LanguageItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    level: str | None = None


class CertificationItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    issuer: str | None = None
    year: int | None = None


class EvidenceQuote(BaseModel):
    """A direct quote from the CV that supports an observation.

    F-16: We replaced binary `team_player: true/false`-style signals (which
    invite bias) with quoted evidence the recruiter can verify in seconds.
    """

    model_config = ConfigDict(extra="ignore")
    observation: str = Field(..., min_length=1, max_length=200)
    quote: str = Field(..., min_length=1, max_length=400)


class CVEnrichmentResult(BaseModel):
    """Shape returned by the CV enrichment prompt."""

    model_config = ConfigDict(extra="ignore")

    personal_summary: str = ""
    executive_summary: str = ""
    location: str = ""
    linkedin_url: str = ""
    github_url: str = ""
    technical_skills: list[SkillItem] = Field(default_factory=list)
    soft_skills: list[SkillItem] = Field(default_factory=list)
    languages: list[LanguageItem] = Field(default_factory=list)
    certifications: list[CertificationItem] = Field(default_factory=list)
    hobbies: list[str] = Field(default_factory=list)
    volunteering: list[str] = Field(default_factory=list)
    total_experience_years: float | None = None
    seniority_estimate: Literal["junior", "mid", "senior", "lead"] | None = None
    strengths: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    evidence_quotes: list[EvidenceQuote] = Field(default_factory=list)
    culture_fit_notes: str = ""

    @field_validator("total_experience_years")
    @classmethod
    def _clamp_experience(cls, v: float | None) -> float | None:
        if v is None:
            return None
        # CVs claiming 60+ years are noise; clamp to a sane range.
        return max(0.0, min(60.0, float(v)))


# ---------------------------------------------------------------------------
# Candidate ↔ job matching
# ---------------------------------------------------------------------------


class JobMatchResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    match_score: int = Field(ge=0, le=100)
    fit_score: int = Field(ge=0, le=100)
    recommendation: Literal["top_candidate", "consider", "not_a_match"]
    reasoning: str = Field(..., min_length=1, max_length=2000)
    strengths_match: list[str] = Field(min_length=1)  # F-23: minimum positives rule
    gaps: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Job offer parsing (paste → structured)
# ---------------------------------------------------------------------------


_SeniorityLiteral = Literal[
    "junior",
    "mid",
    "senior",
    "lead",
    "expert",
    "intern",
    "operator",
    "team_leader",
    "foreman",
    "specialist",
]


class JobParseResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = ""
    department: str | None = None
    location: str | None = None
    role_summary: str | None = None
    team_context: str | None = None
    value_proposition: str | None = None
    remote_constraints: str | None = None
    responsibilities: str = ""
    must_haves: str = ""
    nice_to_haves: str = ""
    tech_stack: str = ""
    benefits: str = ""
    hiring_process: str = ""
    work_mode: Literal["office", "hybrid", "remote", "mobile", "field"] | None = None
    contract_type: Literal["employment", "b2b", "contract", "internship", "temporary"] | None = None
    seniority: _SeniorityLiteral | None = None
    shift_system: (
        Literal["one_shift", "two_shift", "three_shift", "weekend", "equivalent"] | None
    ) = None
    employment_size: (
        Literal["full", "part_50", "part_75", "temporary", "internship", "apprenticeship"] | None
    ) = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    salary_period: Literal["hour", "month", "year"] | None = None
    experience_min_years: int | None = None
    experience_max_years: int | None = None


# ---------------------------------------------------------------------------
# Job attractiveness analysis
# ---------------------------------------------------------------------------


class JobAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    attractiveness_score: int = Field(ge=0, le=100)
    market_position: Literal["above_market", "at_market", "below_market"]
    summary: str = ""
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    candidate_impact: str = ""
    urgency_message: str = ""


# ---------------------------------------------------------------------------
# Job content suggestions
# ---------------------------------------------------------------------------


class JobSuggestResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role_summary: str = ""
    role_purpose: str = ""
    responsibilities: str = ""
    must_haves: str = ""
    nice_to_haves: str = ""
    tech_stack: str = ""
    team_context: str = ""
    success_profile: str = ""
    value_proposition: str = ""
    benefits: str = ""
    hiring_process: str = ""


# ---------------------------------------------------------------------------
# Risk assessment
# ---------------------------------------------------------------------------


class RiskFactor(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    severity: Literal["low", "medium", "high"]


class RiskAssessmentResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    risk_score: int = Field(ge=0, le=100)
    risk_level: Literal["low", "medium", "high"]
    factors: list[RiskFactor] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Map of prompt name → expected schema. Used by BaseLLMService.
# ---------------------------------------------------------------------------

PROMPT_SCHEMA: dict[str, type[BaseModel]] = {
    "cv_enrich": CVEnrichmentResult,
    "job_match": JobMatchResult,
    "job_parse": JobParseResult,
    "job_analysis": JobAnalysisResult,
    "job_suggest": JobSuggestResult,
    "risk_analysis": RiskAssessmentResult,
}
