"""Organizational risk assessment for a job offer via Claude."""
from __future__ import annotations

from typing import Any

from app.services.llm.base import BaseLLMService, LLMResult


class RiskAnalyzer(BaseLLMService):
    """Assesses organizational risk associated with a role."""

    PROMPT_NAME = "risk_analysis"
    MAX_TOKENS = 1024

    async def assess(
        self,
        job_data: dict[str, Any],
        *,
        language: str = "en",
        correlation_id: str | None = None,
    ) -> LLMResult | None:
        payload = self._serialize_payload(job_data)
        return await self._call(
            blocks=[("untrusted_job_offer", payload)],
            language=language,
            correlation_id=correlation_id,
        )
