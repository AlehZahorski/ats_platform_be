"""Job offer attractiveness analysis via Claude."""
from __future__ import annotations

from typing import Any

from app.services.llm.base import BaseLLMService, LLMResult


class JobAnalyzer(BaseLLMService):
    """Analyses a job offer from a candidate's perspective."""

    PROMPT_NAME = "job_analysis"
    MAX_TOKENS = 1024

    async def analyze(
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
