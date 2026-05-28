"""Single source of truth for Anthropic Claude pricing (USD per 1M tokens).

Resolves audit F-11 (duplicated dictionaries in `base.py` and `llm_cv_parser.py`)
and F-12 (silent fallback to Sonnet pricing for unknown models — now we fail
loudly so cost tracking never lies).

Keep this list in sync with https://www.anthropic.com/pricing
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelPricing:
    """USD per 1 000 000 tokens, split by direction."""
    input_per_million: float
    output_per_million: float


# Canonical pricing table. Add new models here only — never inline anywhere else.
PRICING: dict[str, ModelPricing] = {
    "claude-haiku-4-5-20251001": ModelPricing(input_per_million=0.80, output_per_million=4.00),
    "claude-sonnet-4-6": ModelPricing(input_per_million=3.00, output_per_million=15.00),
}


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return cost in USD for a single call. Raises on unknown model (F-12).

    Why raise: silently substituting Sonnet pricing for an unknown model (the
    previous behaviour) under-reported Opus by 5× and made the per-company
    cost dashboard untrustworthy. Better to crash early in dev than to lie
    to finance.
    """
    pricing = PRICING.get(model)
    if pricing is None:
        raise KeyError(
            f"Unknown LLM model {model!r} — add it to "
            f"app.services.llm.pricing.PRICING before using it in production"
        )

    cost_in = pricing.input_per_million * input_tokens / 1_000_000
    cost_out = pricing.output_per_million * output_tokens / 1_000_000
    return round(cost_in + cost_out, 6)


def safe_calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """Variant for cost-logging in hot paths: log a warning instead of raising.

    Use only on the `api_usage_logs` write path where a missing entry should
    not break the user request. Returns None when the model is unknown so the
    caller can decide whether to skip the row.
    """
    try:
        return calculate_cost(model, input_tokens, output_tokens)
    except KeyError as exc:
        logger.warning("LLM pricing unknown — skipping cost row: %s", exc)
        return None
