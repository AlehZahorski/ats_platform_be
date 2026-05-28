"""Prompt-injection defense + PII redaction helpers (audit F-01, F-02).

Two layers of defense for user-controlled content (candidate CVs, recruiter
job paste) going into Claude:

1. **Wrap in XML delimiters** that the system prompt treats as quoted data.
2. **Heuristic sanitiser** that neutralises lines that look like injected
   instructions (`IGNORE PREVIOUS`, `SYSTEM:`, `You are now…`).

The sanitiser is intentionally conservative — it logs and tags every replaced
line so we can audit false positives without losing recruiter signal.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


# Patterns that should never be in legitimate CV/job copy. Case-insensitive.
# Order matters only for the audit log; matching is independent.
_INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ignore_previous",       re.compile(r"\b(ignore|disregard|forget)\s+(all\s+)?(previous|prior|above)\b", re.IGNORECASE)),
    ("system_role",           re.compile(r"^\s*system\s*[:>]", re.IGNORECASE | re.MULTILINE)),
    ("assistant_role",        re.compile(r"^\s*assistant\s*[:>]", re.IGNORECASE | re.MULTILINE)),
    ("you_are_now",           re.compile(r"\byou\s+are\s+(now\s+)?(a\s+)?(\w+\s+){0,3}(model|assistant|ai)\b", re.IGNORECASE)),
    ("new_instructions",      re.compile(r"\bnew\s+instructions?\s*[:>]", re.IGNORECASE)),
    ("override_score",        re.compile(r"\b(score|rate|recommend)\b.*\b(100|max|top|always)\b", re.IGNORECASE)),
    ("jailbreak_dan",         re.compile(r"\b(DAN|do\s+anything\s+now|jailbreak)\b", re.IGNORECASE)),
    ("prompt_leak",           re.compile(r"\b(repeat|print|reveal|show|leak|output)\s+(\w+\s+){0,3}(prompt|instructions|system\s+message)\b", re.IGNORECASE)),
)

# Cap how much we'll log per request — protects logs from a 200-page CV with
# 5000 injection attempts.
_MAX_REPORTED_HITS = 10


def sanitize_untrusted(text: str, *, source: str = "user") -> tuple[str, list[str]]:
    """Strip injection-shaped lines from user-supplied text.

    Returns the cleaned text plus a list of pattern names that were hit. Each
    matched line is replaced by ``[FILTERED:pattern_name]`` so the LLM still
    sees something at that offset (preserves layout) but the imperative is gone.

    Args:
        text: Raw text controlled by the candidate or paste source.
        source: Free-text tag included in the audit log for cross-ref.
    """
    if not text:
        return text, []

    hits: list[str] = []
    cleaned = text

    for name, pattern in _INJECTION_PATTERNS:
        def _replace(match: re.Match[str], _name: str = name) -> str:
            if len(hits) < _MAX_REPORTED_HITS:
                hits.append(_name)
            return f"[FILTERED:{_name}]"

        cleaned = pattern.sub(_replace, cleaned)

    if hits:
        logger.warning(
            "Sanitised %d suspected prompt-injection line(s) from %s content: %s",
            len(hits),
            source,
            ", ".join(sorted(set(hits))),
        )

    return cleaned, hits


def wrap_untrusted(text: str, *, tag: str) -> str:
    """Surround user content with XML-style delimiters.

    The system prompt should tell Claude to treat anything inside
    ``<{tag}>…</{tag}>`` as untrusted data and never as instructions. Tag must
    be a simple identifier (alphanumeric + underscore) — we don't escape it.
    """
    if not re.fullmatch(r"[a-z][a-z0-9_]*", tag):
        raise ValueError(f"Invalid tag {tag!r} — use snake_case ASCII only")

    # Defensive: if the attacker put the closing tag verbatim in the text,
    # neutralise it so they can't "exit" the wrapper from inside.
    safe = text.replace(f"</{tag}>", f"&lt;/{tag}&gt;")
    return f"<{tag}>\n{safe}\n</{tag}>"


# ---------------------------------------------------------------------------
# F-02 — PII redaction (RODO mitigation for opt-out candidates)
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
_PHONE_RE = re.compile(r"(?:\+|00)?\d[\d\s\-()]{7,}\d")


def redact_pii(text: str) -> str:
    """Replace obvious PII (email, phone) with placeholders.

    Used when the candidate has not granted ``ai_profiling`` consent — we still
    want a usable enrichment from Claude (so the recruiter sees the candidate),
    but we don't ship raw email/phone to a US processor. Name redaction is
    deliberately NOT here: removing names breaks executive_summary quality and
    they're already in `parsed_data`, not the LLM scope.
    """
    if not text:
        return text
    text = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = _PHONE_RE.sub("[REDACTED_PHONE]", text)
    return text
