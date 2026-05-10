from __future__ import annotations

import uuid

from app.core.base_service import BaseService
from app.core.enums.jobs import JobStatus
from app.core.exceptions import UnprocessableError
from app.modules.jobs.repository import JobRepository
from app.modules.jobs.schemas import JobCreate, JobOfferAnalysisRead, JobRead, JobSuggestRead, JobUpdate
from app.services.llm_job_analyzer import analyze_job_offer, suggest_job_description


PUBLISH_REQUIREMENTS = {
    "role_summary": "Role summary is required before publishing",
    "role_purpose": "Role purpose is required before publishing",
    "responsibilities": "At least one responsibility is required before publishing",
    "must_haves": "At least one must-have requirement is required before publishing",
    "salary": "Salary range is required before publishing",
    "work_mode": "Work mode is required before publishing",
    "contract_type": "Contract type is required before publishing",
    "location_clarity": "Location or remote clarity is required before publishing",
    "value_proposition": "Value proposition is required before publishing",
    "hiring_process": "Hiring process is required before publishing",
}


class JobService(BaseService[JobRepository]):

    async def create(self, company_id: uuid.UUID, data: JobCreate):
        self._validate_status_transition(data.model_dump())
        return await self.repository.create(company_id, data)

    async def update(self, job, data: JobUpdate):
        next_state = self._merged_job_state(job, data)
        self._validate_status_transition(next_state)
        return await self.repository.update(job, data)

    @classmethod
    def serialize(cls, job) -> JobRead:
        data = JobRead.model_validate(job)
        if job.form_template_link:
            data.template_id = job.form_template_link.template_id
        issues = cls._compute_publish_issues(job)
        data.publish_ready = len(issues) == 0
        data.publish_issues = issues
        return data

    def _validate_status_transition(self, payload: dict) -> None:
        if payload.get("status") != JobStatus.open:
            return
        issues = self._compute_publish_issues(type("JobState", (), payload)())
        if issues:
            raise UnprocessableError({"message": "Job is not ready to publish", "issues": issues})

    @classmethod
    def _compute_publish_issues(cls, job) -> list[str]:
        issues: list[str] = []
        if not cls._has_text(job.role_summary):
            issues.append(PUBLISH_REQUIREMENTS["role_summary"])
        if not cls._has_text(job.role_purpose):
            issues.append(PUBLISH_REQUIREMENTS["role_purpose"])
        if not cls._html_has_content(job.responsibilities):
            issues.append(PUBLISH_REQUIREMENTS["responsibilities"])
        if not cls._html_has_content(job.must_haves):
            issues.append(PUBLISH_REQUIREMENTS["must_haves"])
        if job.salary_min is None or job.salary_max is None or not cls._has_text(job.salary_currency) or not cls._has_text(job.salary_period):
            issues.append(PUBLISH_REQUIREMENTS["salary"])
        if not cls._has_text(job.work_mode):
            issues.append(PUBLISH_REQUIREMENTS["work_mode"])
        if not cls._has_text(job.contract_type):
            issues.append(PUBLISH_REQUIREMENTS["contract_type"])
        if not cls._has_text(job.location) and not cls._has_text(job.remote_constraints):
            issues.append(PUBLISH_REQUIREMENTS["location_clarity"])
        if not cls._has_text(job.value_proposition):
            issues.append(PUBLISH_REQUIREMENTS["value_proposition"])
        if not cls._html_has_content(job.hiring_process):
            issues.append(PUBLISH_REQUIREMENTS["hiring_process"])
        return issues

    def _merged_job_state(self, job, data: JobUpdate) -> dict:
        state = {
            "title": job.title,
            "description": job.description,
            "department": job.department,
            "location": job.location,
            "role_summary": job.role_summary,
            "role_purpose": job.role_purpose,
            "responsibilities": job.responsibilities,
            "must_haves": job.must_haves,
            "nice_to_haves": job.nice_to_haves,
            "tech_stack": job.tech_stack,
            "domain_context": job.domain_context,
            "seniority": job.seniority,
            "experience_min_years": job.experience_min_years,
            "experience_max_years": job.experience_max_years,
            "work_mode": job.work_mode,
            "remote_constraints": job.remote_constraints,
            "success_profile": job.success_profile,
            "team_context": job.team_context,
            "reporting_to": job.reporting_to,
            "value_proposition": job.value_proposition,
            "benefits": job.benefits,
            "hiring_process": job.hiring_process,
            "salary_min": job.salary_min,
            "salary_max": job.salary_max,
            "salary_currency": job.salary_currency,
            "salary_period": job.salary_period,
            "contract_type": job.contract_type,
            "status": job.status,
        }
        state.update(data.model_dump(exclude_unset=True))
        return state

    async def analyze(self, job, language: str = "en") -> JobOfferAnalysisRead:
        job_data = {
            "title": job.title,
            "role_summary": job.role_summary,
            "role_purpose": job.role_purpose,
            "responsibilities": job.responsibilities,
            "must_haves": job.must_haves,
            "nice_to_haves": job.nice_to_haves,
            "tech_stack": job.tech_stack,
            "domain_context": job.domain_context,
            "seniority": str(job.seniority) if job.seniority else None,
            "experience_min_years": job.experience_min_years,
            "experience_max_years": job.experience_max_years,
            "work_mode": str(job.work_mode) if job.work_mode else None,
            "remote_constraints": job.remote_constraints,
            "team_context": job.team_context,
            "success_profile": job.success_profile,
            "value_proposition": job.value_proposition,
            "benefits": job.benefits,
            "hiring_process": job.hiring_process,
            "salary_min": job.salary_min,
            "salary_max": job.salary_max,
            "salary_currency": job.salary_currency,
            "salary_period": str(job.salary_period) if job.salary_period else None,
            "contract_type": str(job.contract_type) if job.contract_type else None,
        }
        result = analyze_job_offer(job_data, language=language)
        result.pop("_meta", None)

        if not result:
            raise UnprocessableError("Job analysis failed — please try again.")

        analysis = JobOfferAnalysisRead(
            attractiveness_score=int(result.get("attractiveness_score", 0)),
            market_position=result.get("market_position", "at_market"),
            summary=result.get("summary", ""),
            strengths=result.get("strengths", []),
            improvements=result.get("improvements", []),
            candidate_impact=result.get("candidate_impact", ""),
            urgency_message=result.get("urgency_message", ""),
        )
        await self.repository.save_analysis(job, analysis)
        return analysis

    async def suggest(self, job, language: str = "en") -> "JobSuggestRead":
        result = suggest_job_description({
            "title": job.title,
            "department": job.department,
            "seniority": str(job.seniority) if job.seniority else None,
            "work_mode": str(job.work_mode) if job.work_mode else None,
            "domain_context": job.domain_context,
        }, language=language)
        if not result:
            raise UnprocessableError("AI suggestion failed — please try again.")
        return JobSuggestRead(**result)

    @staticmethod
    def _has_text(value: str | None) -> bool:
        return bool(value and value.strip())

    @staticmethod
    def _html_has_content(value: str | None) -> bool:
        if not value:
            return False
        import re
        text = re.sub(r"<[^>]+>", "", value).strip()
        return bool(text)
