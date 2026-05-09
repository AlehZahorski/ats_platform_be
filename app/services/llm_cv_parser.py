"""LLM enrichment for CV parsing and candidate-job matching using Claude API."""

from __future__ import annotations

import json
import logging
from typing import Any

import anthropic

from app.core.config import settings

logger = logging.getLogger(__name__)

# Token cost per million (USD) — used for api_usage_logs
_COST_PER_M_INPUT = {
    "claude-haiku-4-5-20251001": 0.80,
    "claude-sonnet-4-6": 3.00,
}
_COST_PER_M_OUTPUT = {
    "claude-haiku-4-5-20251001": 4.00,
    "claude-sonnet-4-6": 15.00,
}

_CV_SYSTEM_PROMPT = """You are an expert CV analyst. You receive structured data already extracted from a CV by a regex parser, plus the raw CV text. Your task is to enrich and correct that data.

Return ONLY a JSON object with exactly these fields. No markdown, no explanation, no code blocks.

{
  "personal_summary": "Verbatim text written by the candidate about themselves (from About Me / Summary section). Empty string if not present.",
  "executive_summary": "3-5 sentences for the recruiter: who this person is, what they do best, what kind of colleague they would be.",
  "location": "City and/or country extracted from CV. Empty string if not found.",
  "linkedin_url": "LinkedIn URL if present. Empty string otherwise.",
  "github_url": "GitHub URL if present. Empty string otherwise.",
  "technical_skills": [{"name": "Python", "level": "advanced"}],
  "soft_skills": [{"name": "Leadership"}],
  "languages": [{"name": "English", "level": "C1"}, {"name": "Polish", "level": "native"}],
  "certifications": [{"name": "AWS Solutions Architect", "issuer": "Amazon", "year": 2023}],
  "hobbies": ["photography", "open source", "climbing"],
  "volunteering": ["Animal shelter volunteer 2022-2023"],
  "total_experience_years": 5.5,
  "seniority_estimate": "senior",
  "strengths": ["Deep backend expertise", "Strong communicator", "Ownership mindset"],
  "red_flags": ["Frequent job changes (3 jobs in 2 years)", "Gap 2021-2022 unexplained"],
  "personality_signals": {
    "team_player": true,
    "team_player_reason": "Mentions collaborative projects and team achievements",
    "leadership_indicators": "Led a team of 5 engineers, mentored junior developers",
    "growth_mindset": "Consistently upskills, multiple certifications, side projects",
    "communication_style": "technical and precise"
  },
  "culture_fit_notes": "Candid and direct communicator based on CV tone. Passion for open source suggests community mindset. Hobbies indicate disciplined and goal-oriented personality."
}

Rules:
- seniority_estimate must be one of: junior, mid, senior, lead
- total_experience_years: calculate from experience dates, return a float
- For array fields, return empty array [] if nothing found, never null
- For string fields, return empty string "" if nothing found, never null
- personality_signals must always be a complete object with all keys
- hobbies and volunteering: extract from dedicated sections AND from mentions in experience descriptions
- LANGUAGE: Write all text values (executive_summary, culture_fit_notes, strengths, red_flags, personality_signals fields) in {language_name}. Keep skill names, tool names and proper nouns in their original form.
"""

_MATCH_SYSTEM_PROMPT = """You are a senior technical recruiter. Evaluate how well a candidate matches a job offer.

Return ONLY a JSON object with exactly these fields. No markdown, no explanation, no code blocks.

{
  "match_score": 78,
  "fit_score": 82,
  "recommendation": "consider",
  "reasoning": "2-3 sentences explaining the overall assessment.",
  "strengths_match": ["Has 5 years Python experience matching the requirement", "Led teams — aligns with leadership expectation"],
  "gaps": ["No Kubernetes experience (nice-to-have)", "Domain knowledge in fintech missing"]
}

Rules:
- match_score (0-100): technical fit — skills, tech stack, seniority, years of experience
- fit_score (0-100): cultural and personal fit — personality signals, hobbies, soft skills, communication style vs team context
- recommendation must be one of: hire, consider, reject
- strengths_match and gaps must be non-empty arrays
- LANGUAGE: Write all text values (reasoning, strengths_match items, gaps items) in {language_name}. Keep skill names, tool names and proper nouns in their original form.
"""


def _calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    cost_in = _COST_PER_M_INPUT.get(model, 3.00) * input_tokens / 1_000_000
    cost_out = _COST_PER_M_OUTPUT.get(model, 15.00) * output_tokens / 1_000_000
    return round(cost_in + cost_out, 6)


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
    return text.strip()


_LANGUAGE_NAMES = {"pl": "Polish", "en": "English"}


def enrich_cv_with_claude(parsed_data: dict[str, Any], raw_text: str, language: str = "en") -> dict[str, Any]:
    """Enrich regex-parsed CV data with Claude.

    Args:
        parsed_data: Output from CVProfileParser.parse() — already structured.
        raw_text: Full raw CV text for context.
        language: Output language code ('en' or 'pl').

    Returns:
        Dict with enriched fields + token_usage + model metadata.
        On any failure returns empty enrichment dict (caller falls back to v1-regex data).
    """
    if not settings.llm_enabled:
        logger.info("LLM disabled (no ANTHROPIC_API_KEY) — skipping CV enrichment")
        return {}

    model = settings.llm_cv_model
    language_name = _LANGUAGE_NAMES.get(language, "English")
    system_prompt = _CV_SYSTEM_PROMPT.replace("{language_name}", language_name)

    user_content = f"""REGEX-PARSED DATA:
{json.dumps(parsed_data, ensure_ascii=False, indent=2)}

RAW CV TEXT:
{raw_text[:8000]}"""

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=model,
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )

        raw_json = _strip_json_fences(response.content[0].text)
        enriched = json.loads(raw_json)

        usage = response.usage
        token_usage = {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "total_tokens": usage.input_tokens + usage.output_tokens,
        }

        enriched["_meta"] = {
            "model": model,
            "token_usage": token_usage,
            "cost_usd": _calculate_cost(model, usage.input_tokens, usage.output_tokens),
        }
        return enriched

    except json.JSONDecodeError as exc:
        logger.warning("LLM returned invalid JSON for CV enrichment: %s", exc)
        return {}
    except anthropic.APIError as exc:
        logger.warning("Anthropic API error during CV enrichment: %s", exc)
        return {}
    except Exception as exc:
        logger.error("Unexpected error during CV enrichment: %s", exc)
        return {}


def match_candidate_to_job(candidate_profile: dict[str, Any], job: dict[str, Any], language: str = "en") -> dict[str, Any]:
    """Score candidate against job using Claude.

    Args:
        candidate_profile: Full candidate profile dict (from CandidateProfile model).
        job: Job data dict (title, must_haves, tech_stack, seniority, etc.).
        language: Output language code ('en' or 'pl').

    Returns:
        Dict with match_score, fit_score, recommendation, reasoning, strengths_match, gaps
        + token_usage + model metadata.
        On any failure returns empty dict (caller skips saving the match).
    """
    if not settings.llm_enabled:
        logger.info("LLM disabled (no ANTHROPIC_API_KEY) — skipping job matching")
        return {}

    model = settings.llm_match_model
    language_name = _LANGUAGE_NAMES.get(language, "English")
    user_content = f"""JOB OFFER:
Title: {job.get("title", "")}
Seniority: {job.get("seniority", "")}
Department: {job.get("department", "")}
Must haves: {json.dumps(job.get("must_haves", []), ensure_ascii=False)}
Tech stack: {json.dumps(job.get("tech_stack", []), ensure_ascii=False)}
Nice to haves: {json.dumps(job.get("nice_to_haves", []), ensure_ascii=False)}
Role summary: {job.get("role_summary", "")}
Team context: {job.get("team_context", "")}
Experience required: {job.get("experience_min_years", "")}-{job.get("experience_max_years", "")} years

CANDIDATE PROFILE:
Seniority: {candidate_profile.get("seniority_estimate", "")}
Total experience: {candidate_profile.get("total_experience_years", "")} years
Technical skills: {json.dumps(candidate_profile.get("technical_skills", []), ensure_ascii=False)}
Soft skills: {json.dumps(candidate_profile.get("soft_skills", []), ensure_ascii=False)}
Languages: {json.dumps(candidate_profile.get("languages", []), ensure_ascii=False)}
Hobbies: {json.dumps(candidate_profile.get("hobbies", []), ensure_ascii=False)}
Strengths: {json.dumps(candidate_profile.get("strengths", []), ensure_ascii=False)}
Red flags: {json.dumps(candidate_profile.get("red_flags", []), ensure_ascii=False)}
Personality: {json.dumps(candidate_profile.get("personality_signals", {}), ensure_ascii=False)}
Culture fit notes: {candidate_profile.get("culture_fit_notes", "")}
Executive summary: {candidate_profile.get("executive_summary", "")}"""

    try:
        match_system_prompt = _MATCH_SYSTEM_PROMPT.replace("{language_name}", language_name)
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=match_system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )

        raw_json = _strip_json_fences(response.content[0].text)
        result = json.loads(raw_json)

        usage = response.usage
        token_usage = {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "total_tokens": usage.input_tokens + usage.output_tokens,
        }

        result["_meta"] = {
            "model": model,
            "token_usage": token_usage,
            "cost_usd": _calculate_cost(model, usage.input_tokens, usage.output_tokens),
        }
        return result

    except json.JSONDecodeError as exc:
        logger.warning("LLM returned invalid JSON for job matching: %s", exc)
        return {}
    except anthropic.APIError as exc:
        logger.warning("Anthropic API error during job matching: %s", exc)
        return {}
    except Exception as exc:
        logger.error("Unexpected error during job matching: %s", exc)
        return {}
