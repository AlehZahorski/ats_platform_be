"""Parses an existing job advertisement (raw text) into structured fields via Claude.

This is intentionally NOT a generator. We extract what's in the source —
never invent, never improve. Used to onboard recruiters who have existing
offers in Word docs, on competitor sites, etc., without retyping them.
"""
from __future__ import annotations

from typing import Any

from app.services.llm.base import BaseLLMService


class JobParser(BaseLLMService):
    PROMPT_NAME = "job_parse"
    MAX_TOKENS = 2048

    def parse(self, raw_text: str, language: str = "en") -> dict[str, Any]:
        # Truncate very long pastes to keep the cost predictable. ~16k chars
        # covers typical job ads with room to spare; longer texts likely
        # contain noise (about-us page, footer) that hurts extraction quality.
        text = raw_text[:16000]
        message = f"JOB ADVERTISEMENT TEXT:\n{text}"
        return self._call(message, language=language)
