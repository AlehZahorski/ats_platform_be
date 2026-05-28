"""Generates job offer content (HTML + plain text fields) from basic metadata via Claude."""
from __future__ import annotations

from typing import Any

from app.services.llm.base import BaseLLMService, LLMResult


class JobSuggester(BaseLLMService):
    """Suggests content for job offer sections based on title, seniority, domain etc."""

    PROMPT_NAME = "job_suggest"
    MAX_TOKENS = 2048

    async def suggest(
        self,
        job_meta: dict[str, Any],
        *,
        language: str = "en",
        correlation_id: str | None = None,
    ) -> LLMResult | None:
        payload = self._serialize_payload(job_meta)
        return await self._call(
            blocks=[("untrusted_job_metadata", payload)],
            language=language,
            correlation_id=correlation_id,
        )
