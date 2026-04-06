from __future__ import annotations

import uuid

from fastapi import HTTPException, status

from app.modules.jobs.repository import JobRepository
from app.modules.jobs.schemas import JobCreate, JobRead, JobUpdate


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


class JobService:
    def __init__(self, repo: JobRepository) -> None:
        self.repo = repo

    async def create(self, company_id: uuid.UUID, data: JobCreate):
        self._validate_status_transition(data.model_dump())
        return await self.repo.create(company_id, data)

    async def update(self, job, data: JobUpdate):
        next_state = self._merged_job_state(job, data)
        self._validate_status_transition(next_state)
        return await self.repo.update(job, data)

    @classmethod
    def serialize(cls, job) -> JobRead:
        data = JobRead.model_validate(job)
        if job.form_template_link:
            data.template_id = job.form_template_link.template_id
        issues = cls._compute_publish_issues(job)
        data.publish_ready = len(issues) == 0
        data.publish_issues = issues
        return data

    def get_publish_issues(self, job) -> list[str]:
        return self._compute_publish_issues(job)

    @classmethod
    def _compute_publish_issues(cls, job) -> list[str]:
        issues: list[str] = []
        if not cls._has_text(job.role_summary):
            issues.append(PUBLISH_REQUIREMENTS["role_summary"])
        if not cls._has_text(job.role_purpose):
            issues.append(PUBLISH_REQUIREMENTS["role_purpose"])
        if not job.responsibilities:
            issues.append(PUBLISH_REQUIREMENTS["responsibilities"])
        if not job.must_haves:
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
        if not job.hiring_process:
            issues.append(PUBLISH_REQUIREMENTS["hiring_process"])
        return issues

    def _validate_status_transition(self, payload: dict) -> None:
        if payload.get("status") != "open":
            return
        issues = self.get_publish_issues(type("JobState", (), payload)())
        if issues:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "Job is not ready to publish", "issues": issues},
            )

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

    @staticmethod
    def _has_text(value: str | None) -> bool:
        return bool(value and value.strip())
