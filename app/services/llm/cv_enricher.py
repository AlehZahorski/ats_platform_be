"""CV enrichment via Claude — wraps the regex parse output with structured signal.

Refactored from the legacy ``app/services/llm_cv_parser.py``:
- prompt moved to ``prompts/cv_enrich.txt``  (F-19)
- async, retried, validated through CVEnrichmentResult  (F-04, F-06, F-07)
- raw text wrapped in <untrusted_cv_text>          (F-01)
- PII redacted when consent not granted          (F-02)
- raw_text length capped by settings              (F-13)
"""
from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.services.llm.base import BaseLLMService, LLMResult
from app.services.llm.safety import redact_pii


class CVEnricher(BaseLLMService):
    PROMPT_NAME = "cv_enrich"
    MAX_TOKENS = 2048

    def __init__(self, model: str | None = None) -> None:
        super().__init__(model or settings.llm_cv_model)

    async def enrich(
        self,
        *,
        parsed_data: dict[str, Any],
        raw_text: str,
        language: str = "en",
        redact_pii_enabled: bool = False,
        correlation_id: str | None = None,
    ) -> LLMResult | None:
        """Enrich a regex-parsed CV.

        Args:
            parsed_data: trusted output of CVProfileParser (already in our DB)
            raw_text: raw CV text — candidate-controlled, sanitised + wrapped
            redact_pii_enabled: if True, scrub email/phone before sending
        """
        text = raw_text or ""
        if len(text) > settings.llm_cv_raw_text_limit:
            text = text[: settings.llm_cv_raw_text_limit]
        if redact_pii_enabled:
            text = redact_pii(text)

        extra = "REGEX-PARSED DATA (trusted, from our own parser):\n" \
                + self._serialize_payload(parsed_data)

        return await self._call(
            blocks=[("untrusted_cv_text", text)],
            language=language,
            extra_context=extra,
            correlation_id=correlation_id,
        )
