"""Lightweight in-process circuit breaker for the Anthropic API (audit F-10).

Counts failures inside a rolling window. After ``threshold`` failures the
breaker opens and ``is_open()`` returns True for ``cool_down_seconds``.
Caller treats an open breaker the same as "LLM disabled" — falls back to
v1-regex, returns 503, etc.

Single process only (in-memory). For horizontal scale, swap the counter
backend to Redis. Not a replacement for a real APM; just a guardrail so a
sudden Anthropic outage doesn't make 100 background CV-parse jobs each
wait 30 seconds for a timeout.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class _State:
    failures: deque[float] = field(default_factory=deque)
    opened_at: float | None = None


class LLMCircuitBreaker:
    """Per-service breaker. Thread-safe but not async-aware (atomic enough)."""

    def __init__(
        self,
        *,
        name: str,
        threshold: int = 5,
        window_seconds: float = 60.0,
        cool_down_seconds: float = 60.0,
    ) -> None:
        self.name = name
        self.threshold = threshold
        self.window_seconds = window_seconds
        self.cool_down_seconds = cool_down_seconds
        self._state = _State()
        self._lock = threading.Lock()

    def is_open(self) -> bool:
        with self._lock:
            if self._state.opened_at is None:
                return False
            if time.monotonic() - self._state.opened_at >= self.cool_down_seconds:
                # Cool-down over — half-open, allow one probe.
                self._state.opened_at = None
                self._state.failures.clear()
                logger.info("LLM breaker %s reset after cool-down", self.name)
                return False
            return True

    def record_success(self) -> None:
        with self._lock:
            self._state.failures.clear()
            self._state.opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            now = time.monotonic()
            # Drop failures older than the window.
            cutoff = now - self.window_seconds
            while self._state.failures and self._state.failures[0] < cutoff:
                self._state.failures.popleft()
            self._state.failures.append(now)

            if len(self._state.failures) >= self.threshold and self._state.opened_at is None:
                self._state.opened_at = now
                logger.error(
                    "LLM breaker %s OPENED after %d failures in %.0fs window — cooling for %.0fs",
                    self.name,
                    len(self._state.failures),
                    self.window_seconds,
                    self.cool_down_seconds,
                )


# Default app-wide breaker. Use per-service breakers if you need finer isolation.
default_breaker = LLMCircuitBreaker(name="anthropic")
