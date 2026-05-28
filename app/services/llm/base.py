"""Base class for Claude-based LLM services — async, validated, cached, monitored.

This file is the single integration point between the Anthropic SDK and the
rest of the app. Every audit-15 finding that lives in code touches this
module:

    F-01 wrap user content with ``<{tag}>…</{tag}>`` + sanitiser
    F-03 ephemeral prompt caching on the system prompt
    F-04 AsyncAnthropic with awaitable ``_call``
    F-06 Pydantic validation of the response
    F-07 timeout (settings) + tenacity retry on 429/529/connection
    F-10 circuit breaker — open breaker degrades to fallback path
    F-11 pricing imported from one place, no inline dicts
    F-14 regex JSON extraction tolerant to preamble / trailing text
    F-18 ``_meta`` separated cleanly so callers don't accidentally leak it
    F-19 every prompt lives in ``prompts/*.txt`` — no inline literals
    F-20 prompt_version (sha256 of the prompt text) shipped in ``_meta`` and
         api_usage_logs
    F-22 correlation_id (provided by caller or auto-uuid) in ``_meta`` and logs

Subclasses declare ``PROMPT_NAME`` and call ``await self._call(message_blocks)``
where ``message_blocks`` is a list of ``(tag, untrusted_text)`` pairs. The
helper does the wrapping, sanitising and assembling so the subclass only
worries about *what* to send, not *how* to ship it safely.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any, ClassVar, TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.services.llm.circuit import default_breaker
from app.services.llm.client import call_with_retry
from app.services.llm.pricing import safe_calculate_cost
from app.services.llm.safety import sanitize_untrusted, wrap_untrusted
from app.services.llm.schemas import PROMPT_SCHEMA, LLMValidationError

logger = logging.getLogger(__name__)

LANGUAGE_NAMES = {"pl": "Polish", "en": "English"}

_PROMPTS_DIR = Path(__file__).parent / "prompts"

# Loaded prompt text + its sha256 — module-level cache keeps re-reads off the
# hot path. Invalidated by restarting the process (acceptable for txt files).
_PROMPT_CACHE: dict[tuple[str, str], tuple[str, str]] = {}


T = TypeVar("T", bound=BaseModel)


class LLMResult(BaseModel):
    """What every ``_call`` returns to the subclass.

    ``data`` is the validated payload. ``meta`` is the bookkeeping (model,
    cost, tokens, prompt_version, correlation_id, retried). Subclasses
    serialize ``data`` to whatever shape callers expect; ``meta`` is logged
    to ``api_usage_logs`` and stripped before responses leave the API.
    """
    data: dict[str, Any]
    meta: dict[str, Any]


class BaseLLMService:
    """Shared logic for all Claude calls."""

    PROMPT_NAME: ClassVar[str] = ""
    MAX_TOKENS: ClassVar[int] = 1024

    def __init__(self, model: str | None = None) -> None:
        self.model = model or settings.llm_cv_model

    # ── Public ────────────────────────────────────────────────────────────

    async def _call(
        self,
        *,
        blocks: list[tuple[str, str]],
        language: str = "en",
        extra_context: str | None = None,
        correlation_id: str | None = None,
    ) -> LLMResult | None:
        """Run a Claude call with the full safety + observability stack.

        Args:
            blocks: list of ``(tag, untrusted_text)`` pairs. Each tag must be
                snake_case ASCII. Each text is sanitised and wrapped in
                ``<{tag}>…</{tag}>`` before being concatenated into the user
                message.
            language: ``'pl'`` or ``'en'`` — substituted into ``{language_name}``
                in the prompt template.
            extra_context: trusted, recruiter-curated context that does NOT
                need to be sanitised (e.g. parsed_data already produced by our
                own regex parser). Prepended as a separate section.
            correlation_id: caller-supplied request id. Auto-generated if None.

        Returns:
            ``LLMResult`` on success. ``None`` when LLM is disabled, breaker
            is open, or any irrecoverable failure occurs — the caller treats
            this exactly like the old "empty dict" sentinel and falls back.
        """
        cid = correlation_id or uuid.uuid4().hex
        log_extra = {"correlation_id": cid, "service": self.__class__.__name__}

        if not settings.llm_enabled:
            logger.info("LLM disabled — skipping", extra=log_extra)
            return None

        if default_breaker.is_open():
            logger.warning("LLM circuit open — skipping call", extra=log_extra)
            return None

        prompt_text, prompt_hash = self._load_prompt(self.PROMPT_NAME, language)
        user_message = self._assemble_user_message(blocks, extra_context=extra_context)
        system_payload = self._build_system_payload(prompt_text)

        try:
            response = await call_with_retry(
                model=self.model,
                max_tokens=self.MAX_TOKENS,
                system=system_payload,
                messages=[{"role": "user", "content": user_message}],
            )
        except anthropic.APIError as exc:
            default_breaker.record_failure()
            logger.warning("Anthropic API error: %s", exc, extra=log_extra)
            return None
        except Exception as exc:  # noqa: BLE001 — last-resort safety net
            default_breaker.record_failure()
            logger.exception("Unexpected LLM error: %s", exc, extra=log_extra)
            return None

        raw_text = response.content[0].text if response.content else ""
        try:
            parsed = self._parse_json(raw_text)
        except LLMValidationError as exc:
            default_breaker.record_failure()
            logger.warning("LLM JSON parse failed: %s", exc, extra=log_extra)
            return None

        # F-06: validate against the per-prompt schema, if registered.
        schema_cls = PROMPT_SCHEMA.get(self.PROMPT_NAME)
        if schema_cls is not None:
            try:
                validated = schema_cls.model_validate(parsed).model_dump()
            except ValidationError as exc:
                default_breaker.record_failure()
                logger.warning(
                    "LLM output failed Pydantic validation: %s — payload keys: %s",
                    exc.errors()[:3],
                    list(parsed.keys()),
                    extra=log_extra,
                )
                return None
            data = validated
        else:
            data = parsed

        default_breaker.record_success()

        usage = response.usage
        input_tokens = getattr(usage, "input_tokens", 0)
        output_tokens = getattr(usage, "output_tokens", 0)
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_create = getattr(usage, "cache_creation_input_tokens", 0) or 0

        meta = {
            "model": self.model,
            "prompt_name": self.PROMPT_NAME,
            "prompt_version": prompt_hash,
            "correlation_id": cid,
            "token_usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_read_tokens": cache_read,
                "cache_creation_tokens": cache_create,
            },
            "cost_usd": safe_calculate_cost(self.model, input_tokens, output_tokens),
        }

        logger.info(
            "LLM call ok service=%s model=%s tokens_in=%d tokens_out=%d cache_read=%d",
            self.__class__.__name__,
            self.model,
            input_tokens,
            output_tokens,
            cache_read,
            extra=log_extra,
        )

        return LLMResult(data=data, meta=meta)

    # ── User message assembly (F-01) ──────────────────────────────────────

    @staticmethod
    def _assemble_user_message(
        blocks: list[tuple[str, str]],
        *,
        extra_context: str | None,
    ) -> str:
        parts: list[str] = []
        if extra_context:
            parts.append(extra_context.strip())
        for tag, text in blocks:
            sanitised, _ = sanitize_untrusted(text or "", source=tag)
            parts.append(wrap_untrusted(sanitised, tag=tag))
        return "\n\n".join(parts)

    # ── Prompt loading (F-19) + versioning (F-20) ─────────────────────────

    @staticmethod
    def _load_prompt(name: str, language: str) -> tuple[str, str]:
        """Returns (prompt_text, sha256_first12_chars)."""
        if not name:
            raise ValueError("PROMPT_NAME must be declared by the subclass")
        cache_key = (name, language)
        if cache_key in _PROMPT_CACHE:
            return _PROMPT_CACHE[cache_key]

        text = (_PROMPTS_DIR / f"{name}.txt").read_text(encoding="utf-8")
        text = text.replace("{language_name}", LANGUAGE_NAMES.get(language, "English"))
        prompt_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
        _PROMPT_CACHE[cache_key] = (text, prompt_hash)
        return text, prompt_hash

    # ── System payload (F-03 ephemeral cache) ─────────────────────────────

    @staticmethod
    def _build_system_payload(prompt_text: str) -> Any:
        """Return either a plain string or a structured cached block.

        Anthropic's prompt-cache requires the block API. Cache is enabled
        only when the prompt is long enough (≥ 1024 tokens, roughly 4 kB) —
        below that it's just overhead. Toggle via settings for local testing.
        """
        if not settings.llm_prompt_cache_enabled:
            return prompt_text
        if len(prompt_text) < 4000:
            return prompt_text  # below Anthropic's caching minimum
        return [
            {
                "type": "text",
                "text": prompt_text,
                "cache_control": {"type": "ephemeral"},
            }
        ]

    # ── JSON parsing (F-14 robust) ────────────────────────────────────────

    _JSON_RE = re.compile(r"\{[\s\S]*\}", re.MULTILINE)

    @classmethod
    def _parse_json(cls, raw: str) -> dict[str, Any]:
        """Pull out the first top-level JSON object, tolerating preamble.

        Order of attempts:
            1. Direct parse — happy path when Claude obeys the "no markdown" rule.
            2. Strip ``\\`\\`\\`json`` / ``\\`\\`\\``` fences.
            3. Greedy regex match on the largest ``{…}`` slab — handles
               "Here is the JSON: {...}" and trailing notes.
        """
        text = (raw or "").strip()
        if not text:
            raise LLMValidationError("empty response")

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Strip ``` fences (with or without "json" suffix).
        stripped = text
        if stripped.startswith("```"):
            stripped = stripped.split("\n", 1)[-1] if "\n" in stripped else stripped[3:]
            if stripped.endswith("```"):
                stripped = stripped.rsplit("```", 1)[0]
        try:
            return json.loads(stripped.strip())
        except json.JSONDecodeError:
            pass

        match = cls._JSON_RE.search(text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError as exc:
                raise LLMValidationError(f"regex JSON candidate invalid: {exc}") from exc

        raise LLMValidationError("no JSON object found in response")

    # ── Misc helpers used by subclasses ───────────────────────────────────

    @staticmethod
    def _serialize_payload(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False, indent=2)
