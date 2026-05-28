"""Deprecated shim — see ``app.services.llm.cv_enricher`` and ``job_matcher``.

This module used to contain inline Anthropic calls + the CV/match system
prompts. The audit_ai_2026_05_28 refactor moved them into
``app.services.llm.cv_enricher.CVEnricher`` and
``app.services.llm.job_matcher.JobMatcher`` with async, validation,
prompt caching and prompt injection defence (see audit findings F-01..F-22).

The old top-level helpers (``enrich_cv_with_claude``, ``match_candidate_to_job``)
are kept here as **synchronous, deprecation-warning** stubs so that any
internal code path we may have missed during the refactor still works — but
they are NO LONGER used by ``app.services.cv_parsing``. Remove this file
once we've confirmed nothing imports from it across one release cycle.
"""
from __future__ import annotations

import asyncio
import warnings
from typing import Any

from app.services.llm.cv_enricher import CVEnricher
from app.services.llm.job_matcher import JobMatcher

_DEPRECATION = (
    "app.services.llm_cv_parser is deprecated — use "
    "app.services.llm.CVEnricher / JobMatcher (async)."
)


def enrich_cv_with_claude(
    parsed_data: dict[str, Any], raw_text: str, language: str = "en"
) -> dict[str, Any]:
    warnings.warn(_DEPRECATION, DeprecationWarning, stacklevel=2)
    enricher = CVEnricher()
    res = asyncio.run(
        enricher.enrich(parsed_data=parsed_data, raw_text=raw_text, language=language)
    )
    if res is None:
        return {}
    return {**res.data, "_meta": res.meta}


def match_candidate_to_job(
    candidate_profile: dict[str, Any], job: dict[str, Any], language: str = "en"
) -> dict[str, Any]:
    warnings.warn(_DEPRECATION, DeprecationWarning, stacklevel=2)
    matcher = JobMatcher()
    res = asyncio.run(
        matcher.match(candidate_profile=candidate_profile, job=job, language=language)
    )
    if res is None:
        return {}
    return {**res.data, "_meta": res.meta}
