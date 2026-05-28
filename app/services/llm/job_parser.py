"""Parses an existing job advertisement (raw text) into structured fields via Claude.

This is intentionally NOT a generator. We extract what's in the source —
never invent, never improve. Used to onboard recruiters who have existing
offers in Word docs, on competitor sites, etc., without retyping them.
"""
from __future__ import annotations

from app.core.config import settings
from app.services.llm.base import BaseLLMService, LLMResult


class JobParser(BaseLLMService):
    PROMPT_NAME = "job_parse"
    MAX_TOKENS = 2048

    async def parse(
        self,
        raw_text: str,
        *,
        language: str = "en",
        correlation_id: str | None = None,
    ) -> LLMResult | None:
        # F-13: truncate via settings (was magic 16000). Longer pastes rarely
        # improve extraction and always raise cost; we log if the cap fires.
        limit = settings.llm_job_raw_text_limit
        text = raw_text or ""
        if len(text) > limit:
            text = text[:limit]
        return await self._call(
            blocks=[("untrusted_job_advert", text)],
            language=language,
            correlation_id=correlation_id,
        )
