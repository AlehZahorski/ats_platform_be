"""Async Anthropic client singleton with timeouts and retries (audit F-04, F-07).

Why a singleton: `anthropic.AsyncAnthropic` opens an `httpx.AsyncClient` per
instance — re-instantiating it on every call (the old code did
`anthropic.Anthropic(api_key=...)` inside `_call`) burns sockets and skips
HTTP keep-alive. One process-wide client is the documented best practice.

Why explicit retry: the SDK has `max_retries` but does not back off on 529
(overloaded). We layer `tenacity` for 429/529 + connection errors. Other
errors propagate so the caller can decide.
"""
from __future__ import annotations

import logging
from typing import Any

import anthropic
from anthropic import AsyncAnthropic
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.core.config import settings

logger = logging.getLogger(__name__)


_client: AsyncAnthropic | None = None


def get_async_client() -> AsyncAnthropic:
    """Process-wide AsyncAnthropic — created lazily on first call."""
    global _client
    if _client is None:
        _client = AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            timeout=settings.llm_request_timeout_seconds,
            # SDK-native retry handles 408/425/429/500/502/503 once by default.
            # Tenacity below handles 529 (overloaded) explicitly with backoff.
            max_retries=0,
        )
    return _client


async def reset_client() -> None:
    """Close the underlying HTTP client (used in tests, graceful shutdown)."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None


def _is_retriable(exc: BaseException) -> bool:
    """Retry on transient API conditions only — never on 4xx (other than 429)."""
    if isinstance(exc, anthropic.APIStatusError):
        return exc.status_code in {429, 502, 503, 504, 529}
    return isinstance(
        exc,
        (anthropic.APITimeoutError, anthropic.APIConnectionError),
    )


async def call_with_retry(**kwargs: Any) -> Any:
    """Call ``client.messages.create`` with exponential-backoff retry.

    Wraps `tenacity` with the policy we want for Anthropic: up to
    `llm_max_retries` attempts, exponential backoff with jitter, only for
    transient errors. Any other exception bubbles immediately.
    """
    client = get_async_client()
    attempts = max(1, settings.llm_max_retries + 1)

    # F-19 (audit_ai_ethics): determinism. Identical CV → identical score.
    # Anthropic default is 1.0 — kept candidates getting different scores
    # on retry, which broke equal-treatment guarantees and made audits
    # impossible to reproduce. Callers can still override via kwargs.
    kwargs.setdefault("temperature", 0.0)

    try:
        async for attempt in AsyncRetrying(
            retry=retry_if_exception(_is_retriable),
            stop=stop_after_attempt(attempts),
            wait=wait_exponential_jitter(initial=1.0, max=10.0, jitter=2.0),
            reraise=True,
        ):
            with attempt:
                return await client.messages.create(**kwargs)
    except RetryError as exc:  # pragma: no cover — tenacity reraises by default
        raise exc.last_attempt.exception() from exc  # type: ignore[misc]
