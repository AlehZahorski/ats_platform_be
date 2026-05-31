"""Candidate ↔ job matching via Claude.

Refactored from the legacy ``app/services/llm_cv_parser.py``:
- prompt moved to ``prompts/job_match.txt``     (F-19)
- async + retry + validated by JobMatchResult   (F-04, F-06, F-07)
- candidate profile and job offer wrapped in separate untrusted blocks (F-01)
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.services.llm.base import BaseLLMService, LLMResult


class JobMatcher(BaseLLMService):
    PROMPT_NAME = "job_match"
    MAX_TOKENS = 1024

    def __init__(self, model: str | None = None) -> None:
        super().__init__(model or settings.llm_match_model)

    async def match(
        self,
        *,
        candidate_profile: dict[str, Any],
        job: dict[str, Any],
        language: str = "en",
        correlation_id: str | None = None,
    ) -> LLMResult | None:
        job_block = self._format_job(job)
        candidate_block = self._format_candidate(candidate_profile)
        return await self._call(
            blocks=[
                ("untrusted_job_offer", job_block),
                ("untrusted_candidate_profile", candidate_block),
            ],
            language=language,
            correlation_id=correlation_id,
        )

    # ── Formatting kept here so the prompt stays format-agnostic ──────────

    @staticmethod
    def _format_job(job: dict[str, Any]) -> str:
        return (
            f"Title: {job.get('title', '')}\n"
            f"Seniority: {job.get('seniority', '')}\n"
            f"Department: {job.get('department', '')}\n"
            f"Must haves: {job.get('must_haves', [])}\n"
            f"Tech stack: {job.get('tech_stack', [])}\n"
            f"Nice to haves: {job.get('nice_to_haves', [])}\n"
            f"Role summary: {job.get('role_summary', '')}\n"
            f"Team context: {job.get('team_context', '')}\n"
            f"Experience required: "
            f"{job.get('experience_min_years', '')}-{job.get('experience_max_years', '')} years"
        )

    @staticmethod
    def _format_candidate(profile: dict[str, Any]) -> str:
        return (
            f"Seniority: {profile.get('seniority_estimate', '')}\n"
            f"Total experience: {profile.get('total_experience_years', '')} years\n"
            f"Technical skills: {profile.get('technical_skills', [])}\n"
            f"Soft skills: {profile.get('soft_skills', [])}\n"
            f"Languages: {profile.get('languages', [])}\n"
            f"Hobbies: {profile.get('hobbies', [])}\n"
            f"Strengths: {profile.get('strengths', [])}\n"
            f"Red flags: {profile.get('red_flags', [])}\n"
            # F-16: evidence_quotes replaced personality_signals
            f"Evidence quotes: {profile.get('evidence_quotes', [])}\n"
            f"Culture fit notes: {profile.get('culture_fit_notes', '')}\n"
            f"Executive summary: {profile.get('executive_summary', '')}"
        )
