from __future__ import annotations

import logging
import re
import unicodedata
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

from pypdf import PdfReader

from app.core.database import AsyncSessionLocal
from app.core.enums.applications import CVParseStatus, ParsingStatus
from app.modules.applications.repository import ApplicationRepository
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
            raise ValueError("DOC files are not supported. Please upload PDF or DOCX.")
        raise ValueError("Unsupported CV file type.")

    @staticmethod
    def _from_pdf(path: Path) -> str:
        reader = PdfReader(str(path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        normalized = _normalize_text(_sanitize(text))
        if not normalized:
            raise ValueError("Could not extract readable text from the PDF.")
        return normalized

    @staticmethod
    def _from_docx(path: Path) -> str:
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml")
        root = ElementTree.fromstring(xml)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        paragraphs = []
        for paragraph in root.findall(".//w:p", ns):
            runs = [node.text for node in paragraph.findall(".//w:t", ns) if node.text]
            if runs:
                paragraphs.append("".join(runs))
        normalized = _normalize_text(_sanitize("\n".join(paragraphs)))
        if not normalized:
            raise ValueError("Could not extract readable text from the DOCX.")
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
        sections: dict[str, list[str]] = {"skills": [], "experience": [], "education": []}
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

    async def run(self, parse_job_id: object) -> None:
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

                normalized = self._parser.parse(raw_text)
                parse_job.raw_result = {
                    "text_length": len(raw_text),
                    "sections_detected": list(SECTION_ALIASES.keys()),
                }
                parse_job.normalized_result = normalized
                parse_job.status = CVParseStatus.review_required
                parse_job.completed_at = datetime.now(UTC)

                await repo.upsert_candidate_profile(
                    parse_job.application_id,
                    headline=normalized.get("headline"),
                    summary=normalized.get("summary"),
                    skills=normalized.get("skills", []),
                    experience=normalized.get("experience", []),
                    education=normalized.get("education", []),
                    parsing_status=ParsingStatus.review_required,
                    parsing_error=None,
                    last_parsed_at=parse_job.completed_at,
                )
                await db.commit()
            except Exception as exc:
                await db.rollback()
                logger.error("CV parsing failed for job %s: %s", parse_job_id, exc)
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
