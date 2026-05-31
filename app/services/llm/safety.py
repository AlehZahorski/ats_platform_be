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
    (
        "ignore_previous",
        re.compile(
            r"\b(ignore|disregard|forget)\s+(all\s+)?(previous|prior|above)\b", re.IGNORECASE
        ),
    ),
    ("system_role", re.compile(r"^\s*system\s*[:>]", re.IGNORECASE | re.MULTILINE)),
    ("assistant_role", re.compile(r"^\s*assistant\s*[:>]", re.IGNORECASE | re.MULTILINE)),
    (
        "you_are_now",
        re.compile(
            r"\byou\s+are\s+(now\s+)?(a\s+)?(\w+\s+){0,3}(model|assistant|ai)\b", re.IGNORECASE
        ),
    ),
    ("new_instructions", re.compile(r"\bnew\s+instructions?\s*[:>]", re.IGNORECASE)),
    (
        "override_score",
        re.compile(r"\b(score|rate|recommend)\b.*\b(100|max|top|always)\b", re.IGNORECASE),
    ),
    ("jailbreak_dan", re.compile(r"\b(DAN|do\s+anything\s+now|jailbreak)\b", re.IGNORECASE)),
    (
        "prompt_leak",
        re.compile(
            r"\b(repeat|print|reveal|show|leak|output)\s+(\w+\s+){0,3}(prompt|instructions|system\s+message)\b",
            re.IGNORECASE,
        ),
    ),
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


def redact_pii(text: str, *, names: list[str] | None = None) -> str:
    """Replace personal data (email, phone, candidate name) with placeholders.

    Runs before any CV text leaves our process for the LLM — this is what backs
    the public /ai-info promise: "przed wysłaniem czegokolwiek do modelu
    automatycznie redagujemy dane osobowe (PII)", and "analiza opiera się na
    kompetencjach, a nie na tożsamości".

    Email and phone are matched heuristically. The candidate name is NOT
    guessed from capitalisation — we redact only the exact tokens the regex
    parser already extracted (``first_name`` / ``last_name``), so we never
    accidentally scrub a skill, company or city. Names are kept in our own
    ``parsed_data`` for the recruiter; they simply never reach the model.

    Args:
        text: raw CV text controlled by the candidate.
        names: known name tokens to redact verbatim (e.g. ["Jan", "Kowalski"]).
    """
    if not text:
        return text
    text = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = _PHONE_RE.sub("[REDACTED_PHONE]", text)
    for token in names or []:
        token = (token or "").strip()
        if len(token) < 2:
            continue  # skip initials / empty — too short to match safely
        text = re.sub(
            rf"\b{re.escape(token)}\b",
            "[REDACTED_NAME]",
            text,
            flags=re.IGNORECASE,
        )
    return text
