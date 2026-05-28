"""Organizational risk assessment for a job offer via Claude."""
from __future__ import annotations

from typing import Any

from app.services.llm.base import BaseLLMService


class RiskAnalyzer(BaseLLMService):
    """Assesses organizational risk associated with a role.

    Returns dict with: risk_score (0-100), risk_level (low/medium/high),
    factors (list of {name, severity}), recommendations (list of strings) —
    plus `_meta`. Empty dict on any failure.
    """

    PROMPT_NAME = "risk_analysis"
    MAX_TOKENS = 1024

    def assess(self, job_data: dict[str, Any], language: str = "en") -> dict[str, Any]:
        message = f"JOB OFFER DATA FOR RISK ASSESSMENT:\n{self._serialize_payload(job_data)}"
        return self._call(message, language=language)
