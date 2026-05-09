"""LLM analysis of job offers for candidate attractiveness and market positioning."""

from __future__ import annotations

import json
import logging
from typing import Any

import anthropic

from app.core.config import settings

logger = logging.getLogger(__name__)

_COST_PER_M_INPUT = {
    "claude-haiku-4-5-20251001": 0.80,
    "claude-sonnet-4-6": 3.00,
}
_COST_PER_M_OUTPUT = {
    "claude-haiku-4-5-20251001": 4.00,
    "claude-sonnet-4-6": 15.00,
}

_SYSTEM_PROMPT = """You are a senior talent acquisition expert and employer branding specialist. \
Analyze this job offer from a candidate's perspective and provide honest, actionable insights for the recruiter.

Return ONLY a JSON object with exactly these fields. No markdown, no explanation, no code blocks.

{
  "attractiveness_score": 72,
  "market_position": "at_market",
  "summary": "2-3 sentences: honest overall assessment of the offer's appeal to candidates.",
  "strengths": [
    "Remote-first policy is highly valued by candidates",
    "Modern tech stack attracts strong engineers"
  ],
  "improvements": [
    "No salary range disclosed — 60% of candidates skip offers without compensation data",
    "Requirements list too long — consider moving some items to nice-to-haves"
  ],
  "candidate_impact": "A great engineer in this role could reduce deployment time by 40% and unblock the entire product team.",
  "urgency_message": "Companies with transparent, well-structured offers fill positions 2× faster and attract 3× more qualified applicants."
}

Rules:
- attractiveness_score: integer 0–100 reflecting overall candidate appeal
- market_position: exactly one of: above_market, at_market, below_market
- strengths: 2–5 specific, concrete strengths (empty array [] if none found)
- improvements: 2–5 specific, actionable suggestions (empty array [] if none needed)
- candidate_impact: 1–2 sentences on why hiring the right person matters for the company — personalize to the role
- urgency_message: 1–2 motivational sentences for the recruiter about offer quality
- Be honest and direct — vague, salary-hidden offers score lower; transparent, well-structured ones score higher
- LANGUAGE: Write all text values (summary, strengths, improvements, candidate_impact, urgency_message) in {language_name}. Keep technical terms and proper nouns in their original form.
"""


_LANGUAGE_NAMES = {"pl": "Polish", "en": "English"}


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


def analyze_job_offer(job_data: dict[str, Any], language: str = "en") -> dict[str, Any]:
    """Analyze a job offer for candidate attractiveness using Claude.

    Returns dict with analysis fields + ``_meta`` (model, tokens, cost).
    On any failure returns an empty dict — caller must handle gracefully.
    """
    if not settings.llm_enabled:
        logger.info("LLM disabled (no ANTHROPIC_API_KEY) — skipping job offer analysis")
        return {}

    model = settings.llm_cv_model  # haiku: fast and cost-effective for structured analysis
    system_prompt = _SYSTEM_PROMPT.replace("{language_name}", _LANGUAGE_NAMES.get(language, "English"))

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": f"JOB OFFER DATA:\n{json.dumps(job_data, ensure_ascii=False, indent=2)}",
                }
            ],
        )

        raw_json = _strip_json_fences(response.content[0].text)
        result = json.loads(raw_json)

        usage = response.usage
        result["_meta"] = {
            "model": model,
            "token_usage": {
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
            },
            "cost_usd": _calculate_cost(model, usage.input_tokens, usage.output_tokens),
        }
        return result

    except json.JSONDecodeError as exc:
        logger.warning("LLM returned invalid JSON for job analysis: %s", exc)
        return {}
    except anthropic.APIError as exc:
        logger.warning("Anthropic API error during job analysis: %s", exc)
        return {}
    except Exception as exc:
        logger.error("Unexpected error during job analysis: %s", exc)
        return {}


_SUGGEST_SYSTEM_PROMPT = """You are a senior technical recruiter who writes compelling job offer content. \
Given basic job metadata, generate content for each section of a job offer.

Return ONLY a JSON object with exactly these fields. No markdown, no explanation, no code blocks.

PLAIN TEXT fields (no HTML tags — just regular text):
  "role_summary"    — 2-3 engaging sentences, what the role is about
  "role_purpose"    — 1-2 sentences, why this position exists and its impact
  "team_context"    — 1-2 sentences, team size, methodology, atmosphere
  "success_profile" — 1-2 sentences, what kind of person thrives here

HTML fields (use <ul><li>...</li></ul> for lists, <strong> for emphasis, no <p> wrappers needed):
  "responsibilities"  — HTML list, 5-8 items
  "must_haves"        — HTML list, 4-7 items
  "nice_to_haves"     — HTML list, 3-5 items
  "tech_stack"        — HTML list of technologies
  "value_proposition" — HTML, 2-3 sentences about culture/growth/impact
  "benefits"          — HTML list, 4-6 items
  "hiring_process"    — HTML ordered list, 3-5 numbered steps

Example output:
{
  "role_summary": "We're looking for a Senior Backend Engineer to lead the design of mission-critical systems. You'll set technical standards and mentor junior engineers while shipping features that impact thousands of users.",
  "role_purpose": "This role exists to own the reliability and scalability of our core API as we triple our user base this year.",
  "team_context": "You'll join a 6-person backend squad working in 2-week sprints with strong DevOps culture and minimal meetings.",
  "success_profile": "The ideal candidate is self-directed, communicates clearly, and has a bias for simple solutions over complex abstractions.",
  "responsibilities": "<ul><li>Design and build scalable REST APIs...</li><li>Lead code reviews and architectural decisions</li></ul>",
  "must_haves": "<ul><li>3+ years of Python experience</li><li>Strong knowledge of PostgreSQL</li></ul>",
  "nice_to_haves": "<ul><li>Experience with FastAPI</li><li>Familiarity with Kubernetes</li></ul>",
  "tech_stack": "<ul><li>Python / FastAPI</li><li>PostgreSQL / Redis</li><li>Docker / GitHub Actions</li></ul>",
  "value_proposition": "<strong>Real ownership</strong> — you'll shape the architecture, not just execute tickets. We offer full remote flexibility and a team that values your craft.",
  "benefits": "<ul><li>Remote-first, flexible hours</li><li>Private healthcare (Medicover)</li><li>5000 PLN annual learning budget</li></ul>",
  "hiring_process": "<ol><li>CV review (1-2 days)</li><li>Intro call with HR (30 min)</li><li>Technical interview with team (60 min)</li><li>Decision within 5 business days</li></ol>"
}

Rules:
- Generate realistic, specific content tailored to the job title, seniority and domain provided
- Professional but human language — no buzzwords or generic filler
- Plain text fields: no HTML tags whatsoever
- HTML fields: valid HTML only, no markdown
- LANGUAGE: Write ALL content in {language_name}. Keep technology names, tool names and proper nouns in their original form (e.g. Python, PostgreSQL, React stay as-is).
"""


def suggest_job_description(job_meta: dict[str, Any], language: str = "en") -> dict[str, Any]:
    """Generate AI-suggested HTML content for a job offer based on basic metadata.

    Returns dict with HTML field values. On any failure returns an empty dict.
    """
    if not settings.llm_enabled:
        logger.info("LLM disabled — skipping job description suggestion")
        return {}

    model = settings.llm_cv_model
    system_prompt = _SUGGEST_SYSTEM_PROMPT.replace("{language_name}", _LANGUAGE_NAMES.get(language, "English"))

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=model,
            max_tokens=2048,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": f"JOB METADATA:\n{json.dumps(job_meta, ensure_ascii=False, indent=2)}",
                }
            ],
        )

        raw_json = _strip_json_fences(response.content[0].text)
        return json.loads(raw_json)

    except json.JSONDecodeError as exc:
        logger.warning("LLM returned invalid JSON for job suggestion: %s", exc)
        return {}
    except anthropic.APIError as exc:
        logger.warning("Anthropic API error during job suggestion: %s", exc)
        return {}
    except Exception as exc:
        logger.error("Unexpected error during job suggestion: %s", exc)
        return {}
