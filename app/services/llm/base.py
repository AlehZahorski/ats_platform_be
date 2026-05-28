"""Base class for Claude-based LLM services.

Each concrete service declares:
- ``PROMPT_NAME`` — filename (without .txt) in services/llm/prompts/
- ``MAX_TOKENS`` — Claude max_tokens for the response

And exposes domain-specific methods that build the user message and call ``self._call(...)``.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, ClassVar

import anthropic

from app.core.config import settings

logger = logging.getLogger(__name__)

# Pricing per 1M tokens (USD) — fallback for unknown models uses Sonnet pricing
_COST_PER_M_INPUT = {
    "claude-haiku-4-5-20251001": 0.80,
    "claude-sonnet-4-6": 3.00,
}
_COST_PER_M_OUTPUT = {
    "claude-haiku-4-5-20251001": 4.00,
    "claude-sonnet-4-6": 15.00,
}

LANGUAGE_NAMES = {"pl": "Polish", "en": "English"}

_PROMPTS_DIR = Path(__file__).parent / "prompts"


class BaseLLMService:
    """Shared logic for Claude calls — prompt loading, JSON parsing, cost tracking."""

    PROMPT_NAME: ClassVar[str] = ""
    MAX_TOKENS: ClassVar[int] = 1024

    def __init__(self, model: str | None = None) -> None:
        self.model = model or settings.llm_cv_model

    # ── Public ────────────────────────────────────────────────────────────

    def _call(self, user_message: str, language: str = "en") -> dict[str, Any]:
        """Invoke Claude. Returns parsed JSON dict (with `_meta`), or `{}` on any failure."""
        if not settings.llm_enabled:
            logger.info("LLM disabled — skipping %s", self.__class__.__name__)
            return {}

        system_prompt = self._load_prompt(self.PROMPT_NAME, language)

        try:
            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            response = client.messages.create(
                model=self.model,
                max_tokens=self.MAX_TOKENS,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            raw = self._strip_json_fences(response.content[0].text)
            result: dict[str, Any] = json.loads(raw)

            usage = response.usage
            result["_meta"] = {
                "model": self.model,
                "token_usage": {
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                },
                "cost_usd": self._calculate_cost(usage.input_tokens, usage.output_tokens),
            }
            return result

        except json.JSONDecodeError as exc:
            logger.warning("LLM returned invalid JSON in %s: %s", self.__class__.__name__, exc)
            return {}
        except anthropic.APIError as exc:
            logger.warning("Anthropic API error in %s: %s", self.__class__.__name__, exc)
            return {}
        except Exception as exc:  # noqa: BLE001 — safety net for unforeseen errors
            logger.error("Unexpected error in %s: %s", self.__class__.__name__, exc)
            return {}

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _load_prompt(name: str, language: str) -> str:
        if not name:
            raise ValueError("PROMPT_NAME must be declared by the subclass")
        text = (_PROMPTS_DIR / f"{name}.txt").read_text(encoding="utf-8")
        return text.replace("{language_name}", LANGUAGE_NAMES.get(language, "English"))

    @staticmethod
    def _strip_json_fences(text: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            if text.endswith("```"):
                text = text.rsplit("```", 1)[0]
        return text.strip()

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        cost_in = _COST_PER_M_INPUT.get(self.model, 3.00) * input_tokens / 1_000_000
        cost_out = _COST_PER_M_OUTPUT.get(self.model, 15.00) * output_tokens / 1_000_000
        return round(cost_in + cost_out, 6)

    @staticmethod
    def _serialize_payload(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False, indent=2)
