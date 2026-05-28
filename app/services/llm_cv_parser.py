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

_CV_SYSTEM_PROMPT = """You are an expert CV analyst committed to fair, evidence-based candidate evaluation. You receive structured data already extracted from a CV by a regex parser, plus the raw CV text. Your task is to enrich and correct that data.

BIAS-PROTECTION RULES (MUST follow strictly):

A. PROTECTED ATTRIBUTES — Do NOT infer or use as signal: gender, age, ethnicity, religion, marital status, sexual orientation, disability, nationality. If a field would require such inference, leave it neutral. Do not guess gender from first name or age from graduation year.

B. EVIDENCE-ONLY — Every assessment must cite concrete CV evidence. Never speculate about personality from indirect cues (photo, hobbies alone, place of birth). "Likes climbing" does not imply risk tolerance; "Played team sports" does not imply teamwork.

C. RED FLAGS — Only flag with HARD evidence: unexplained employment gap > 12 months at mid/senior level, explicitly stated reason for concern, demonstrably false claims. Job-change frequency is NOT a red flag in itself — in many markets and career stages it is normal. Career switches are NOT a red flag.

D. CULTURE FIT — Only describe what the CV explicitly shows. No personality typing, no "vibe" assessments. If you cannot say something concrete and evidence-based, leave culture_fit_notes empty.

Return ONLY a JSON object with exactly these fields. No markdown, no explanation, no code blocks.

{
  "personal_summary": "Verbatim text written by the candidate about themselves (from About Me / Summary section). Empty string if not present.",
  "executive_summary": "3-5 sentences for the recruiter: who this person is, what they do best, what kind of colleague they would be. Based on CV evidence only.",
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
  "strengths": ["Deep backend expertise (5y Python, led 3 production systems)", "Strong communicator (presented at 3 conferences)"],
  "red_flags": ["Unexplained 18-month gap 2021-2022"],
  "personality_signals": {
    "team_player": true,
    "team_player_reason": "Explicitly mentions collaborative projects and team achievements with concrete examples",
    "leadership_indicators": "Led a team of 5 engineers, mentored junior developers",
    "growth_mindset": "Consistently upskills, multiple certifications, side projects",
    "communication_style": "technical and precise"
  },
  "culture_fit_notes": "Evidence-based observations from CV: communication style, collaboration patterns explicitly described in role descriptions. Leave empty if no concrete evidence."
}

Rules:
- seniority_estimate must be one of: junior, mid, senior, lead
- total_experience_years: calculate from experience dates, return a float
- For array fields, return empty array [] if nothing found, never null
- For string fields, return empty string "" if nothing found, never null
- personality_signals must always be a complete object with all keys; each field may be empty string if no evidence
- hobbies and volunteering: extract from dedicated sections AND from mentions in experience descriptions
- red_flags: PREFER empty array over speculation. Only HARD evidence (rule C above).
- LANGUAGE: Write all text values (executive_summary, culture_fit_notes, strengths, red_flags, personality_signals fields) in {language_name}. Keep skill names, tool names and proper nouns in their original form.
"""

_MATCH_SYSTEM_PROMPT = """You are a senior recruiter committed to fair, evidence-based candidate evaluation. Your output INFORMS a human recruiter — it never decides. Apply the eight fairness rules below RIGOROUSLY before scoring.

FAIRNESS PRINCIPLES — non-negotiable:

1. TRANSFERABLE SKILLS — Programming languages transfer. A "PHP developer" applying for a "Software Engineer" role is qualified by the fact they program — they are NOT disqualified by a different language tag. Specific tool/framework/language gaps that can be learned on the job in 1-3 months are NOT critical gaps; mention them in strengths_match as "could quickly pick up X".

2. REQUIRED vs NICE-TO-HAVE — Failing on must_haves matters. Missing nice_to_haves is NEVER grounds to reject — at most a minor note.

3. POTENTIAL > LABELS — Career switchers, self-taught engineers, candidates with non-traditional paths but strong portfolio: score on capability and growth trajectory, not pedigree. Strong learning signals (certifications, side projects, GitHub activity) count as positive.

4. DOMAIN TRANSFER — If the role does not require domain-specific expertise (e.g. production line work, customer service, general admin), do NOT down-score for an unrelated industry background. A teacher applying for a production role brings discipline, reliability and team coordination — these are POSITIVES, not flags.

5. NO PROXIES — Score capability only. Do NOT factor in: graduation year (age proxy), first/last name (gender/ethnicity proxy), location of birth, photo, marital status, nationality. If you notice yourself reasoning about any of these, stop and re-anchor on skills.

6. CULTURAL CONTEXT — Job-change frequency, gap patterns and career trajectories differ across markets. Frequent short stints early in career are normal in Poland for the 2018-2024 cohort. Do not flag unless 4+ jobs in 2 years at senior level.

7. CONSERVATIVE NOT_A_MATCH — Use "not_a_match" ONLY when there is clear, evident inadequacy: cashier with no marketing background applying for Regional Director, candidate claiming 10+ years experience but CV shows 1 year, or absolute absence of fundamentals required by the role. Two or more critical must-have gaps AT a seniority delta of 2+ levels. NEVER use "not_a_match" because of a single missing nice-to-have or different tool stack.

8. HUMAN-IN-LOOP — Your recommendation is a hint for a human, not a verdict. When uncertain, prefer "consider" over "not_a_match". Always assume there will be a short verification interview before any decision.

MINIMUM POSITIVES RULE — strengths_match MUST contain at least 1 item for every candidate, even those receiving "not_a_match". Find something — every CV has something.

Return ONLY a JSON object with exactly these fields. No markdown, no explanation, no code blocks.

{
  "match_score": 78,
  "fit_score": 82,
  "recommendation": "consider",
  "reasoning": "2-3 sentences explaining capability match. Mention transferable skills if relevant. State if seniority is aligned.",
  "strengths_match": ["Has 5 years Python experience — directly satisfies the must-have", "Led 8-person team — exceeds the leadership requirement", "PHP background means programming fundamentals transfer immediately to Python role"],
  "gaps": ["No Kubernetes experience — listed only as nice-to-have", "Domain knowledge in fintech missing — onboarding will need 1-2 months of context"]
}

Rules:
- match_score (0-100): capability fit — what the candidate CAN do, including transferable skills, not just exact label match. A PHP dev applying to a Python role with no other gaps should score 70+, not 30.
- fit_score (0-100): soft fit — communication patterns, teamwork evidence, growth orientation visible in CV. Based on EVIDENCE only, never on assumptions.
- recommendation must be one of: top_candidate, consider, not_a_match
   • top_candidate — meets must_haves at the right seniority, plus strong evidence of relevant capability. Invite to interview immediately.
   • consider — has core capability but not 100% on every requirement, OR borderline seniority, OR strong potential signal that needs verification. Human reviewer should look closer.
   • not_a_match — see rule 7 above. Reserved for clear inadequacy or fabricated claims.
- strengths_match: MINIMUM 1 item, always. Concrete and evidence-based, citing the CV.
- gaps: list only must-have gaps with concrete impact. Nice-to-have gaps belong in strengths_match as "could be developed". If there are no real gaps, return empty array [].
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
