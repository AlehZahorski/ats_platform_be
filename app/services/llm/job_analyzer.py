"""Job offer attractiveness analysis via Claude."""
from __future__ import annotations

from typing import Any

from app.services.llm.base import BaseLLMService


class JobAnalyzer(BaseLLMService):
    """Analyses a job offer from a candidate's perspective.

    Returns dict with: attractiveness_score, market_position, summary,
    strengths, improvements, candidate_impact, urgency_message — plus `_meta`.
    Empty dict on any failure.
    """

    PROMPT_NAME = "job_analysis"
    MAX_TOKENS = 1024

    def analyze(self, job_data: dict[str, Any], language: str = "en") -> dict[str, Any]:
        message = f"JOB OFFER DATA:\n{self._serialize_payload(job_data)}"
        return self._call(message, language=language)
