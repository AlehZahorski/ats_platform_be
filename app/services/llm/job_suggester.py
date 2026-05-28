"""Generates job offer content (HTML + plain text fields) from basic metadata via Claude."""
from __future__ import annotations

from typing import Any

from app.services.llm.base import BaseLLMService


class JobSuggester(BaseLLMService):
    """Suggests content for job offer sections based on title, seniority, domain etc.

    Returns dict with: role_summary, role_purpose, responsibilities, must_haves,
    nice_to_haves, tech_stack, team_context, success_profile, value_proposition,
    benefits, hiring_process — plus `_meta`.
    Empty dict on any failure.
    """

    PROMPT_NAME = "job_suggest"
    MAX_TOKENS = 2048

    def suggest(self, job_meta: dict[str, Any], language: str = "en") -> dict[str, Any]:
        message = f"JOB METADATA:\n{self._serialize_payload(job_meta)}"
        return self._call(message, language=language)
