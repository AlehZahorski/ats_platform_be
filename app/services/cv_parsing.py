from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

from pypdf import PdfReader

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.i18n import detect_text_language, t
from app.core.enums.applications import CVParseStatus, ParsingStatus
from app.modules.applications.repository import ApplicationRepository
from app.services.llm import CVEnricher, JobMatcher
from app.services.cv_keywords import (
    DEGREE_WORDS,
    EDUCATION_WORDS,
    PERSONAL_INFO_ALIASES,
    PRESENT_WORDS,
    ROLE_WORDS,
    SECTION_ALIASES,
    SKILL_KEYWORDS,
)

logger = logging.getLogger(__name__)

CV_PARSE_TIMEOUT = 120


# ---------------------------------------------------------------------------
# CVTextExtractor — Single Responsibility: read raw text from PDF/DOCX files
# ---------------------------------------------------------------------------

class CVTextExtractor:
    """Extracts raw text from CV files. Supports PDF and DOCX."""

    def extract(self, path: str) -> str:
        file_path = Path(path)
        suffix = file_path.suffix.lower()
        if suffix == ".pdf":
            return self._from_pdf(file_path)
        if suffix == ".docx":
            return self._from_docx(file_path)
        if suffix == ".doc":
            raise ValueError(t("cv.doc_not_supported"))
        raise ValueError(t("cv.unsupported_type"))

    @staticmethod
    def _from_pdf(path: Path) -> str:
        reader = PdfReader(str(path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        normalized = _normalize_text(_sanitize(text))
        if not normalized:
            raise ValueError(t("cv.pdf_unreadable"))
        # F-15: cap raw text we keep around. 200k chars covers PhD-length
        # CVs with publications; anything longer is noise and would only
        # blow up later truncation steps.
        if len(normalized) > settings.llm_cv_extract_char_limit:
            logger.warning(
                "PDF CV truncated to %d chars (was %d)",
                settings.llm_cv_extract_char_limit,
                len(normalized),
            )
            normalized = normalized[: settings.llm_cv_extract_char_limit]
        return normalized

    @staticmethod
    def _from_docx(path: Path) -> str:
        # SECURITY: defusedxml protects against XXE / billion-laughs in user uploads.
        try:
            from defusedxml.ElementTree import fromstring as _safe_fromstring  # type: ignore
        except ImportError:  # pragma: no cover — defusedxml is in requirements
            _safe_fromstring = ElementTree.fromstring  # type: ignore[assignment]

        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml")
        root = _safe_fromstring(xml)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        paragraphs = []
        for paragraph in root.findall(".//w:p", ns):
            runs = [node.text for node in paragraph.findall(".//w:t", ns) if node.text]
            if runs:
                paragraphs.append("".join(runs))
        normalized = _normalize_text(_sanitize("\n".join(paragraphs)))
        if not normalized:
            raise ValueError(t("cv.docx_unreadable"))
        if len(normalized) > settings.llm_cv_extract_char_limit:
            logger.warning(
                "DOCX CV truncated to %d chars (was %d)",
                settings.llm_cv_extract_char_limit,
                len(normalized),
            )
            normalized = normalized[: settings.llm_cv_extract_char_limit]
        return normalized


# ---------------------------------------------------------------------------
# CVProfileParser — Single Responsibility: parse structured data from CV text
# ---------------------------------------------------------------------------

class CVProfileParser:
    """Parses a structured candidate profile from raw CV text.
    Keyword data lives in cv_keywords.py."""

    def parse(self, text: str) -> dict:
        normalized = _normalize_text(text)
        lines = normalized.splitlines()
        email = self._find_email(normalized)
        phone = self._find_phone(normalized)
        first_name, last_name = self._infer_name(lines, email, phone)
        headline = self._infer_headline(lines, first_name, last_name)
        summary = self._infer_summary(lines, headline, email, phone)
        sections = self._collect_sections(lines)
        skills = self._extract_skills(lines, sections.get("skills", []))
        experience = self._extract_experience(sections.get("experience", []))
        education = self._extract_education(sections.get("education", []))
        return {
            "first_name": first_name or "",
            "last_name": last_name or "",
            "email": email or "",
            "phone": phone,
            "headline": headline,
            "summary": summary,
            "skills": [{"name": skill} for skill in skills],
            "experience": experience,
            "education": education,
        }

    # ── Contact extraction ────────────────────────────────────────────────────

    @staticmethod
    def _find_email(text: str) -> str | None:
        match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, re.IGNORECASE)
        return match.group(0) if match else None

    @staticmethod
    def _find_phone(text: str) -> str | None:
        match = re.search(r"(?:(?:\+|00)\d{1,3}[\s-]?)?(?:\(?\d{2,4}\)?[\s-]?)?[\d\s-]{6,}", text)
        return re.sub(r"\s+", " ", match.group(0)).strip() if match else None

    # ── Name / headline / summary inference ──────────────────────────────────

    def _infer_name(
        self, lines: list[str], email: str | None, phone: str | None
    ) -> tuple[str | None, str | None]:
        for index, line in enumerate(lines[:20]):
            cleaned = line.strip()
            canonical = _canonicalize(cleaned)
            if canonical in {"name", "imie", "nazwisko i imie"} and index + 1 < len(lines):
                return _split_name(lines[index + 1])
            if canonical.startswith(("name", "imie", "nazwisko i imie")):
                possible = re.sub(
                    r"^(name|imię|imie|nazwisko i imię|nazwisko i imie)\s*:?\s*",
                    "", cleaned, flags=re.IGNORECASE,
                )
                split = _split_name(possible)
                if any(split):
                    return split

        for line in lines[:8]:
            cleaned = line.strip()
            if not cleaned or cleaned in {email, phone}:
                continue
            if "@" in cleaned or re.search(r"https?://|linkedin|github", cleaned, re.IGNORECASE):
                continue
            split = _split_name(cleaned)
            if any(split):
                return split
        return None, None

    def _infer_headline(
        self, lines: list[str], first_name: str | None, last_name: str | None
    ) -> str | None:
        for line in lines[:20]:
            cleaned = line.strip()
            if not cleaned:
                continue
            if first_name and last_name and cleaned.lower() == f"{first_name} {last_name}".lower():
                continue
            if "@" in cleaned or len(cleaned) < 4:
                continue
            if (
                self._is_section_heading(cleaned)
                or self._is_personal_heading(cleaned)
                or _looks_like_personal_metadata(cleaned)
            ):
                continue
            return cleaned
        return None

    def _infer_summary(
        self,
        lines: list[str],
        headline: str | None,
        email: str | None,
        phone: str | None,
    ) -> str | None:
        summary_lines: list[str] = []
        for line in lines[:20]:
            cleaned = line.strip()
            if not cleaned or cleaned in {headline, email, phone}:
                continue
            if self._is_section_heading(cleaned):
                break
            if self._is_personal_heading(cleaned) or _looks_like_personal_metadata(cleaned):
                continue
            if len(cleaned.split()) >= 6:
                summary_lines.append(cleaned)
            if len(" ".join(summary_lines)) > 280:
                break
        return " ".join(summary_lines[:3]) or None

    # ── Section collection ────────────────────────────────────────────────────

    def _collect_sections(self, lines: list[str]) -> dict[str, list[str]]:
        sections: dict[str, list[str]] = {key: [] for key in SECTION_ALIASES}
        current: str | None = None
        for line in lines:
            matched = self._match_section(line)
            if matched:
                current = matched
                continue
            if self._looks_like_new_section(line):
                current = None
                continue
            if current:
                sections[current].append(line.strip())
        return sections

    def _match_section(self, value: str) -> str | None:
        canonical = _normalize(_canonicalize(value))
        for section, aliases in SECTION_ALIASES.items():
            if canonical in {_normalize(a) for a in aliases}:
                return section
        return None

    def _is_section_heading(self, value: str) -> bool:
        return self._match_section(value) is not None

    def _is_personal_heading(self, value: str) -> bool:
        canonical = _canonicalize(value)
        return canonical in {_canonicalize(alias) for alias in PERSONAL_INFO_ALIASES}

    def _looks_like_new_section(self, value: str) -> bool:
        cleaned = value.strip(": ").strip()
        if self._is_section_heading(cleaned) or self._is_personal_heading(cleaned):
            return True
        if _looks_like_date_range(cleaned):
            return False
        if _looks_like_role_or_company(cleaned, ROLE_WORDS) or _looks_like_school_line(cleaned, EDUCATION_WORDS):
            return False
        return bool(
            re.fullmatch(r"[A-ZĄĆĘŁŃÓŚŹŻ][A-ZĄĆĘŁŃÓŚŹŻ /&()'\-]{3,}", cleaned)
            and len(cleaned.split()) <= 8
        )

    # ── Skills extraction ─────────────────────────────────────────────────────

    def _extract_skills(self, lines: list[str], section_lines: list[str]) -> list[str]:
        candidates = section_lines or lines
        seen: list[str] = []
        for line in candidates:
            cleaned_line = re.sub(r"^[A-Za-zÀ-ÿ /-]+:\s*", "", line)
            parts = [
                p.strip(" -•,;:") for p in re.split(r"[,|/•]", cleaned_line)
                if p.strip(" -•,;:")
            ]
            for part in parts:
                lowered = part.lower()
                if lowered in SKILL_KEYWORDS and _format_skill(part) not in seen:
                    seen.append(_format_skill(part))
                elif 1 <= len(part.split()) <= 4 and any(char.isalpha() for char in part):
                    if lowered not in {"mother tongue(s)", "communication", "management"} and _looks_like_skill(part, SKILL_KEYWORDS):
                        formatted = _format_skill(part)
                        if formatted not in seen:
                            seen.append(formatted)
        return seen[:20]

    # ── Experience / education extraction ─────────────────────────────────────

    def _extract_experience(self, lines: list[str]) -> list[dict]:
        if not lines:
            return []
        entries = self._parse_timeline_entries(lines, kind="experience")
        return [
            {
                "title": entry.get("title"),
                "company": entry.get("company"),
                "date_range": entry.get("date_range"),
                "description": entry.get("description"),
            }
            for entry in entries[:8]
            if any(entry.values())
        ]

    def _extract_education(self, lines: list[str]) -> list[dict]:
        if not lines:
            return []
        entries = self._parse_timeline_entries(lines, kind="education")
        return [
            {
                "school": entry.get("school"),
                "degree": entry.get("degree"),
                "date_range": entry.get("date_range"),
                "description": entry.get("description"),
            }
            for entry in entries[:6]
            if any(entry.values())
        ]

    def _parse_timeline_entries(self, lines: list[str], kind: str) -> list[dict[str, str | None]]:
        entries: list[dict[str, str | None]] = []
        current = _empty_entry(kind)

        for raw_line in lines:
            line = _cleanup_line(raw_line)
            if not line or _is_noise_line(line) or self._match_section(line):
                continue

            if _looks_like_date_range(line):
                if _has_entry_content(current):
                    entries.append(_finalize_entry(current, kind))
                    current = _empty_entry(kind)
                current["date_range"] = line
                continue

            if kind == "experience":
                if not current["title"] and _looks_like_role_or_company(line, ROLE_WORDS):
                    title, company = _split_role_company(line)
                    current["title"] = title or line
                    if company:
                        current["company"] = company
                    continue
                if current["title"] and not current["company"] and _looks_like_company_line(line):
                    current["company"] = line
                    continue
            else:
                if not current["school"] and _looks_like_school_line(line, EDUCATION_WORDS):
                    current["school"] = line
                    continue
                if current["school"] and not current["degree"] and _looks_like_degree_line(line, DEGREE_WORDS):
                    current["degree"] = line
                    continue

            current["description_lines"].append(line)  # type: ignore[union-attr]

        if _has_entry_content(current):
            entries.append(_finalize_entry(current, kind))
        return [entry for entry in entries if any(entry.values())]


# ---------------------------------------------------------------------------
# CVParsingService — Single Responsibility: orchestrate the parse pipeline
# ---------------------------------------------------------------------------

class CVParsingService:
    """Orchestrates the full CV parsing pipeline: fetch job → extract → parse → persist."""

    def __init__(self) -> None:
        self._extractor = CVTextExtractor()
        self._parser = CVProfileParser()
        # F-04: stateless async LLM services, re-used across invocations.
        self._enricher = CVEnricher()
        self._matcher = JobMatcher()

    async def run(self, parse_job_id: object) -> None:
        # F-22: one correlation id per parse job — links the parse_job row,
        # api_usage_logs rows and structured log lines.
        correlation_id = uuid.uuid4().hex

        async with AsyncSessionLocal() as db:
            repo = ApplicationRepository(db)
            parse_job = await repo.get_cv_parse_job(parse_job_id)
            if not parse_job:
                return

            parse_job.status = CVParseStatus.extracting
            parse_job.started_at = datetime.now(UTC)
            parse_job.error_message = None
            await db.commit()

            try:
                raw_text = self._extractor.extract(parse_job.cv_url or "")
                parse_job.raw_text = raw_text
                parse_job.status = CVParseStatus.parsing
                await db.commit()

                # Step 1: regex parser extracts structured facts
                normalized = self._parser.parse(raw_text)
                parse_job.raw_result = {
                    "text_length": len(raw_text),
                    "sections_detected": list(SECTION_ALIASES.keys()),
                }

                # Step 2: LLM enriches the regex output.
                # F-02: redact PII when the candidate has not granted explicit
                # consent for AI profiling. The recruiter still gets a regex
                # summary; the LLM call sees [REDACTED_*] placeholders.
                application = parse_job.application
                consent_granted = bool(
                    application and application.ai_profiling_consented_at
                )
                redact = (
                    settings.llm_redact_pii_without_consent
                    and not consent_granted
                )

                cv_lang = detect_text_language(
                    (raw_text or "")[:2000],
                    fallback=parse_job.language or "en",
                )
                enrich_res = await self._enricher.enrich(
                    parsed_data=normalized,
                    raw_text=raw_text,
                    language=cv_lang,
                    redact_pii_enabled=redact,
                    correlation_id=correlation_id,
                )
                enriched: dict = enrich_res.data if enrich_res else {}
                llm_meta: dict = enrich_res.meta if enrich_res else {}
                parser_version = "v2-llm" if enriched else "v1-regex"

                if llm_meta:
                    parse_job.llm_model = llm_meta.get("model")
                    parse_job.token_usage = llm_meta.get("token_usage")

                parse_job.normalized_result = {**normalized, **enriched}
                parse_job.parser_version = parser_version
                parse_job.status = CVParseStatus.completed
                parse_job.completed_at = datetime.now(UTC)

                profile = await repo.upsert_candidate_profile(
                    parse_job.application_id,
                    headline=normalized.get("headline"),
                    summary=normalized.get("summary"),
                    skills=normalized.get("skills", []),
                    experience=normalized.get("experience", []),
                    education=normalized.get("education", []),
                    parsing_status=ParsingStatus.completed,
                    parsing_error=None,
                    last_parsed_at=parse_job.completed_at,
                    parser_version=parser_version,
                    personal_summary=enriched.get("personal_summary") or None,
                    executive_summary=enriched.get("executive_summary") or None,
                    location=enriched.get("location") or None,
                    linkedin_url=enriched.get("linkedin_url") or None,
                    github_url=enriched.get("github_url") or None,
                    technical_skills=enriched.get("technical_skills"),
                    soft_skills=enriched.get("soft_skills"),
                    languages=enriched.get("languages"),
                    certifications=enriched.get("certifications"),
                    hobbies=enriched.get("hobbies"),
                    volunteering=enriched.get("volunteering"),
                    total_experience_years=enriched.get("total_experience_years"),
                    seniority_estimate=enriched.get("seniority_estimate") or None,
                    strengths=enriched.get("strengths"),
                    red_flags=enriched.get("red_flags"),
                    # F-16: legacy personality_signals not written by the new
                    # prompt — left None on new rows. Read path stays unchanged.
                    personality_signals=None,
                    evidence_quotes=enriched.get("evidence_quotes"),
                    culture_fit_notes=enriched.get("culture_fit_notes") or None,
                )
                await db.commit()

                # Step 3: log API usage cost per company
                if llm_meta:
                    application = parse_job.application
                    if application:
                        from app.modules.jobs.models import Job
                        job_result = await db.get(Job, application.job_id)
                        if job_result:
                            await repo.save_api_usage_log(
                                company_id=job_result.company_id,
                                operation="cv_parsing",
                                meta=llm_meta,
                            )
                            await db.commit()

                # Step 4: automatic job matching (only with AI-profiling consent
                # AND a successful enrichment).
                if enriched and profile and consent_granted:
                    await self._run_matching(
                        repo, db, parse_job, profile,
                        correlation_id=correlation_id,
                    )
                elif enriched and profile and not consent_granted:
                    logger.info(
                        "Skipping automatic job matching — no ai_profiling consent",
                        extra={"correlation_id": correlation_id},
                    )

            except Exception as exc:
                await db.rollback()
                logger.error(
                    "CV parsing failed for job %s: %s",
                    parse_job_id, exc,
                    extra={"correlation_id": correlation_id},
                )
                parse_job.status = CVParseStatus.failed
                parse_job.error_message = str(exc)[:500]
                parse_job.completed_at = datetime.now(UTC)
                await repo.upsert_candidate_profile(
                    parse_job.application_id,
                    headline=None,
                    summary=None,
                    skills=[],
                    experience=[],
                    education=[],
                    parsing_status=ParsingStatus.failed,
                    parsing_error=str(exc)[:500],
                    last_parsed_at=parse_job.completed_at,
                )
                await db.commit()

    async def _run_matching(
        self, repo, db, parse_job, profile,
        *, correlation_id: str,
    ) -> None:
        """Run automatic LLM matching after successful CV enrichment.

        F-09: short-circuit when an existing match with the same idempotency
        key is found — avoids a paid Claude call when the candidate's profile
        and the job snapshot have not changed.
        """
        from app.modules.jobs.models import Job
        application = parse_job.application
        if not application:
            return

        job = await db.get(Job, application.job_id)
        if not job:
            return

        job_data = {
            "title": job.title,
            "seniority": job.seniority,
            "department": job.department,
            "must_haves": job.must_haves,
            "tech_stack": job.tech_stack,
            "nice_to_haves": job.nice_to_haves,
            "role_summary": job.role_summary,
            "team_context": job.team_context,
            "experience_min_years": job.experience_min_years,
            "experience_max_years": job.experience_max_years,
        }
        profile_data = {
            "seniority_estimate": profile.seniority_estimate,
            "total_experience_years": profile.total_experience_years,
            "technical_skills": profile.technical_skills or [],
            "soft_skills": profile.soft_skills or [],
            "languages": profile.languages or [],
            "hobbies": profile.hobbies or [],
            "strengths": profile.strengths or [],
            "red_flags": profile.red_flags or [],
            # F-16: evidence_quotes carries the recruiter-actionable signal now.
            "evidence_quotes": profile.evidence_quotes or [],
            "culture_fit_notes": profile.culture_fit_notes,
            "executive_summary": profile.executive_summary,
        }

        # F-09: idempotency. Hash of profile + job snapshot used as a unique
        # key — a repeat call with the same content is a no-op.
        match_key = _build_match_key(
            candidate_profile_id=str(profile.id),
            job=job,
            profile_data=profile_data,
        )
        existing = await repo.get_job_match_by_key(match_key)
        if existing is not None:
            logger.info(
                "Skipping match — idempotent hit on key %s",
                match_key[:12],
                extra={"correlation_id": correlation_id},
            )
            return

        match_sample = " ".join(
            filter(
                None,
                (
                    job.title,
                    job.role_summary,
                    job.role_purpose,
                    job.must_haves,
                    job.team_context,
                    job.value_proposition,
                ),
            )
        )
        match_lang = detect_text_language(match_sample, fallback=parse_job.language or "en")
        match_res = await self._matcher.match(
            candidate_profile=profile_data,
            job=job_data,
            language=match_lang,
            correlation_id=correlation_id,
        )
        if match_res is None:
            return

        match_data = match_res.data
        match_meta = match_res.meta

        await repo.save_job_match(
            application_id=application.id,
            candidate_profile_id=profile.id,
            job_id=job.id,
            match_result={**match_data, "_meta": match_meta},
            match_key=match_key,
        )

        if match_meta:
            await repo.save_api_usage_log(
                company_id=job.company_id,
                operation="job_matching",
                meta=match_meta,
            )
        await db.commit()


# ---------------------------------------------------------------------------
# F-09 — match idempotency
# ---------------------------------------------------------------------------


def _build_match_key(
    *,
    candidate_profile_id: str,
    job,
    profile_data: dict,
) -> str:
    """sha256(profile_id|job_id|job.updated_at|profile_signature).

    profile_signature is a stable JSON of the fields that actually influence
    the match (skills, seniority, summary). Changing the candidate's name or
    email does NOT invalidate the cache — bias-by-name protection.
    """
    signature = {
        "seniority": profile_data.get("seniority_estimate"),
        "years": profile_data.get("total_experience_years"),
        "tech": sorted(
            (s.get("name", "") if isinstance(s, dict) else str(s))
            for s in profile_data.get("technical_skills", []) or []
        ),
        "languages": sorted(
            (s.get("name", "") if isinstance(s, dict) else str(s))
            for s in profile_data.get("languages", []) or []
        ),
        "summary": profile_data.get("executive_summary"),
    }
    job_updated = getattr(job, "updated_at", None)
    job_updated_iso = job_updated.isoformat() if job_updated else ""
    payload = json.dumps(
        {
            "profile_id": candidate_profile_id,
            "job_id": str(job.id),
            "job_updated_at": job_updated_iso,
            "signature": signature,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Module-level singletons and backward-compatible entry point
# ---------------------------------------------------------------------------

cv_parsing_service = CVParsingService()


async def run_cv_parse_job(parse_job_id: object) -> None:
    """Entry point kept for backward compatibility. Delegates to CVParsingService."""
    await cv_parsing_service.run(parse_job_id)


# ---------------------------------------------------------------------------
# Private helpers (pure functions shared between extractor and parser)
# ---------------------------------------------------------------------------

def _sanitize(text: str) -> str:
    return text.replace("\x00", "")


def _normalize_text(text: str) -> str:
    cleaned_lines = []
    for line in text.replace("\r", "").splitlines():
        cleaned = re.sub(r"\s+", " ", line).strip()
        if cleaned:
            cleaned_lines.append(cleaned)
    return "\n".join(cleaned_lines)


def _canonicalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    without_marks = "".join(char for char in normalized if not unicodedata.combining(char))
    lowered = without_marks.lower().strip()
    lowered = re.sub(r"[•·▪●◆■*]+", " ", lowered)
    lowered = re.sub(r"[^a-z0-9/&+() -]+", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered.strip(" :|-")


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"\s+", " ", text)
    return text


def _split_name(value: str) -> tuple[str | None, str | None]:
    words = re.findall(r"[A-Za-zÀ-ÿ'-]+", value)
    if 2 <= len(words) <= 4 and all(word[0].isalpha() for word in words[:2]):
        return words[0].title(), words[-1].title()
    return None, None


def _cleanup_line(value: str) -> str:
    return re.sub(r"^[•·▪●◆■*\-•]+\s*", "", value).strip()


def _looks_like_date_range(value: str) -> bool:
    canonical = _canonicalize(value)
    if any(word in canonical for word in PRESENT_WORDS) and re.search(r"\d{4}", canonical):
        return True
    patterns = (
        r"\b\d{2}[./-]\d{2}[./-]\d{4}\b",
        r"\b\d{4}\b",
        r"\b\d{2}[./-]\d{4}\b",
    )
    matches = sum(1 for pattern in patterns if re.search(pattern, canonical))
    return matches >= 1 and any(token in canonical for token in ("-", "–", "—", "/", "do", "to"))


def _looks_like_role_or_company(value: str, role_words: frozenset[str]) -> bool:
    if _looks_like_date_range(value) or _looks_like_subsection_heading(value):
        return False
    canonical = _canonicalize(value)
    return any(word in canonical.split() for word in role_words) or value.isupper()


def _looks_like_company_line(value: str) -> bool:
    if _looks_like_date_range(value) or _looks_like_subsection_heading(value):
        return False
    if len(value.split()) > 6:
        return False
    return not value.endswith(":")


def _looks_like_school_line(value: str, education_words: frozenset[str]) -> bool:
    if _looks_like_date_range(value):
        return False
    canonical = _canonicalize(value)
    return any(word in canonical for word in education_words) or value.isupper()


def _looks_like_degree_line(value: str, degree_words: frozenset[str]) -> bool:
    if _looks_like_date_range(value):
        return False
    canonical = _canonicalize(value)
    return any(word in canonical for word in degree_words) or len(value.split()) <= 8


def _looks_like_subsection_heading(value: str) -> bool:
    canonical = _canonicalize(value)
    if canonical in {"technologies practices", "technologies & practices", "dodatkowo", "additional information"}:
        return True
    return value.endswith(":") and len(value.split()) <= 5


def _looks_like_skill(value: str, skill_keywords: frozenset[str]) -> bool:
    if value.lower() in skill_keywords:
        return True
    return bool(re.fullmatch(r"[A-Za-z0-9.+#-]{2,25}", value))


def _looks_like_personal_metadata(value: str) -> bool:
    lowered = _canonicalize(value)
    metadata_starts = (
        "nationality", "date of birth", "place of birth", "gender",
        "linkedin", "github", "email", "email address", "phone",
        "adres e mail", "telefon", "narodowosc", "data urodzenia",
        "miejsce urodzenia", "plec", "obywatelstwo", "zezwolenie na prace",
    )
    return lowered.startswith(metadata_starts)


def _split_role_company(value: str) -> tuple[str | None, str | None]:
    separators = [" | ", " - ", " — ", " – ", " @ ", " at "]
    for separator in separators:
        if separator in value:
            left, right = value.split(separator, 1)
            if left.strip() and right.strip():
                return left.strip(), right.strip()
    words = value.split()
    if value.upper() == value and len(words) >= 3:
        return " ".join(words[:-1]).title(), words[-1].title()
    return None, None


def _format_skill(value: str) -> str:
    lowered = value.lower()
    if lowered == "aws":
        return "AWS"
    if lowered == "sql":
        return "SQL"
    return value if value.isupper() else value.title()


def _is_noise_line(value: str) -> bool:
    lowered = _canonicalize(value)
    return lowered in {"page 1 / 2", "page 2 / 2", "strona 1 / 2", "strona 2 / 2"}


def _empty_entry(kind: str) -> dict[str, object]:
    if kind == "experience":
        return {"title": None, "company": None, "date_range": None, "description_lines": []}
    return {"school": None, "degree": None, "date_range": None, "description_lines": []}


def _has_entry_content(entry: dict[str, object]) -> bool:
    return any([
        entry.get("title"), entry.get("company"), entry.get("school"),
        entry.get("degree"), entry.get("date_range"), bool(entry.get("description_lines")),
    ])


def _finalize_entry(entry: dict[str, object], kind: str) -> dict[str, str | None]:
    description_lines = [
        line for line in entry["description_lines"]  # type: ignore[union-attr]
        if not _looks_like_subsection_heading(line)
    ]
    description = " ".join(description_lines).strip() or None
    if kind == "experience":
        return {
            "title": entry["title"],  # type: ignore[dict-item]
            "company": entry["company"],  # type: ignore[dict-item]
            "date_range": entry["date_range"],  # type: ignore[dict-item]
            "description": description,
        }
    return {
        "school": entry["school"],  # type: ignore[dict-item]
        "degree": entry["degree"],  # type: ignore[dict-item]
        "date_range": entry["date_range"],  # type: ignore[dict-item]
        "description": description,
    }
