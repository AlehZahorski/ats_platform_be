"""JobService — thin orchestrator.

Delegates concerns to focused collaborators:
- Validation     → PublishValidator, StatusTransitionValidator
- Persistence    → JobRepository, AnalysisRepository, RiskItemRepository, MitigationActionRepository
- LLM           → JobAnalyzer, JobSuggester, RiskAnalyzer
"""
from __future__ import annotations

import uuid
from typing import Any

from app.core.base_service import BaseService
from app.core.exceptions import UnprocessableError
from app.core.i18n import detect_text_language, t
from app.modules.jobs.models import Job, MitigationAction, RiskItem
from app.modules.jobs.repository import (
    AnalysisRepository,
    JobRepository,
    MitigationActionRepository,
    RiskItemRepository,
)
from app.modules.jobs.schemas import (
    JobCreate,
    JobOfferAnalysisRead,
    JobRead,
    JobRiskAssessmentRead,
    JobSuggestRead,
    JobUpdate,
    MitigationActionCreate,
    MitigationActionUpdate,
    RiskItemCreate,
    RiskItemUpdate,
)
from app.modules.jobs.validators import PublishValidator, StatusTransitionValidator
from app.services.llm import JobAnalyzer, JobParser, JobSuggester, RiskAnalyzer


# Fields passed to each LLM service — kept as module constants for clarity.
_ANALYZE_FIELDS: tuple[str, ...] = (
    "title", "role_summary", "role_purpose", "responsibilities",
    "must_haves", "nice_to_haves", "tech_stack", "domain_context",
    "seniority", "experience_min_years", "experience_max_years",
    "work_mode", "remote_constraints", "team_context", "success_profile",
    "value_proposition", "benefits", "hiring_process",
    "salary_min", "salary_max", "salary_currency", "salary_period",
    "contract_type",
)

_RISK_FIELDS: tuple[str, ...] = (
    "title", "department", "role_purpose", "role_scope", "role_deliverables",
    "must_haves", "tech_stack", "domain_context",
    "seniority", "experience_min_years", "team_context",
    "salary_min", "salary_max", "salary_currency", "salary_period",
    "work_mode",
)

_SUGGEST_FIELDS: tuple[str, ...] = (
    "title", "department", "seniority", "work_mode", "domain_context",
)


class JobService(BaseService[JobRepository]):

    def __init__(self, repository: JobRepository) -> None:
        super().__init__(repository)
        # Sibling repositories sharing the same AsyncSession
        self.analysis_repo = AnalysisRepository(repository.db)
        self.risk_item_repo = RiskItemRepository(repository.db)
        self.mitigation_repo = MitigationActionRepository(repository.db)
        # Stateless LLM services
        self._job_analyzer = JobAnalyzer()
        self._job_suggester = JobSuggester()
        self._risk_analyzer = RiskAnalyzer()

    # ── Core CRUD ─────────────────────────────────────────────────────────

    async def create(self, company_id: uuid.UUID, data: JobCreate) -> Job:
        StatusTransitionValidator.validate(data.model_dump())
        return await self.repository.create(company_id, data)

    async def update(self, job: Job, data: JobUpdate) -> Job:
        StatusTransitionValidator.validate(self._merged_state(job, data))
        return await self.repository.update(job, data)

    async def parse_text(self, raw_text: str, language: str = "en") -> dict[str, Any]:
        """Extract structured fields from an existing job advertisement text.

        Returns whatever the LLM could extract; the frontend then patches
        only the non-empty fields into the editor state. Never raises —
        returns empty dict if LLM is unavailable.
        """
        parser = JobParser()
        result = parser.parse(raw_text, language=language)
        # Strip _meta from response (cost tracking key not exposed to client)
        result.pop("_meta", None)
        return result

    async def clone(self, source: Job) -> Job:
        """Duplicate a job offer.

        Copies the structured content (title, requirements, salary, etc.) but
        intentionally resets:
          - status      → "draft" (clone must be reviewed before publishing)
          - suggest_used_at → None (clone is allowed a fresh AI suggest call)
          - publish-related dates / external ids — none persisted here
          - linked form template, AI analyses, risk items — NOT copied
        The new job gets a "(kopia)" suffix in the title for quick visual diff.
        """
        suffix = " (kopia)"
        new_title = source.title if source.title.endswith(suffix) else f"{source.title}{suffix}"
        payload = JobCreate(
            title=new_title,
            department=source.department,
            location=source.location,
            status="draft",
            category=source.category,
            shift_system=source.shift_system,
            employment_size=source.employment_size,
            required_qualifications=list(source.required_qualifications or []),
            role_summary=source.role_summary,
            role_purpose=source.role_purpose,
            role_scope=source.role_scope,
            role_deliverables=source.role_deliverables,
            responsibilities=source.responsibilities,
            must_haves=source.must_haves,
            nice_to_haves=source.nice_to_haves,
            tech_stack=source.tech_stack,
            domain_context=source.domain_context,
            seniority=source.seniority,
            experience_min_years=source.experience_min_years,
            experience_max_years=source.experience_max_years,
            work_mode=source.work_mode,
            remote_constraints=source.remote_constraints,
            contract_type=source.contract_type,
            salary_min=source.salary_min,
            salary_max=source.salary_max,
            salary_currency=source.salary_currency,
            salary_period=source.salary_period,
            success_profile=source.success_profile,
            team_context=source.team_context,
            reporting_to=source.reporting_to,
            value_proposition=source.value_proposition,
            benefits=source.benefits,
            hiring_process=source.hiring_process,
        )
        return await self.repository.create(source.company_id, payload)

    @classmethod
    def serialize(cls, job: Job) -> JobRead:
        data = JobRead.model_validate(job)
        if job.form_template_link:
            data.template_id = job.form_template_link.template_id
        issues = PublishValidator.validate(job)
        data.publish_ready = len(issues) == 0
        data.publish_issues = issues
        return data

    # ── LLM: attractiveness analysis (persisted → JobAnalysis) ───────────

    async def analyze(self, job: Job, language: str = "en") -> JobOfferAnalysisRead:
        issues = PublishValidator.validate(job)
        if issues:
            raise UnprocessableError({
                "message": t("jobs.not_ready_for_analysis"),
                "issues": issues,
            })
        effective_lang = self._resolve_language(job, language)
        raw = self._job_analyzer.analyze(
            self._job_to_dict(job, _ANALYZE_FIELDS),
            language=effective_lang,
        )
        result = self._llm_or_fail(raw, "jobs.analysis_failed")

        analysis = JobOfferAnalysisRead(
            attractiveness_score=int(result.get("attractiveness_score", 0)),
            market_position=result.get("market_position", "at_market"),
            summary=result.get("summary", ""),
            strengths=result.get("strengths", []),
            improvements=result.get("improvements", []),
            candidate_impact=result.get("candidate_impact", ""),
            urgency_message=result.get("urgency_message", ""),
        )

        await self.analysis_repo.upsert_analysis(job.id, {
            "score": analysis.attractiveness_score,
            "market_position": analysis.market_position,
            "summary": analysis.summary,
            "strengths": analysis.strengths,
            "improvements": analysis.improvements,
            "candidate_impact": analysis.candidate_impact,
            "urgency_message": analysis.urgency_message,
        })
        return analysis

    # ── LLM: risk assessment (persisted → JobRiskAssessment) ─────────────

    async def assess_risk(self, job: Job, language: str = "en") -> JobRiskAssessmentRead:
        effective_lang = self._resolve_language(job, language)
        raw = self._risk_analyzer.assess(
            self._job_to_dict(job, _RISK_FIELDS),
            language=effective_lang,
        )
        result = self._llm_or_fail(raw, "jobs.risk_assessment_failed")

        row = await self.analysis_repo.upsert_risk_assessment(job.id, {
            "score": int(result.get("risk_score", 0)),
            "level": result.get("risk_level", "medium"),
            "factors": result.get("factors", []),
            "recommendations": result.get("recommendations", []),
        })
        return JobRiskAssessmentRead.model_validate(row)

    # ── LLM: content suggestion (not persisted) ───────────────────────────

    async def suggest(self, job: Job, language: str = "en") -> JobSuggestRead:
        # One-time gate — refuse if starters were already generated for this job.
        if job.suggest_used_at is not None:
            raise UnprocessableError(t("jobs.suggest_already_used"))

        # Suggest is special — for empty drafts the offer has no content yet,
        # so the fallback (interface language) wins almost always. That is OK:
        # the user filling a fresh form expects suggestions in their UI lang.
        effective_lang = self._resolve_language(job, language)
        raw = self._job_suggester.suggest(
            self._job_to_dict(job, _SUGGEST_FIELDS),
            language=effective_lang,
        )
        result = self._llm_or_fail(raw, "jobs.suggest_failed")

        # Mark used — even if user discards the output, this was a paid call.
        from datetime import UTC, datetime
        job.suggest_used_at = datetime.now(UTC)
        await self.repository.db.flush()

        return JobSuggestRead(**result)

    # ── Risk items CRUD ───────────────────────────────────────────────────

    async def add_risk_item(self, job: Job, data: RiskItemCreate) -> RiskItem:
        return await self.risk_item_repo.add(job.id, data)

    async def update_risk_item(self, item: RiskItem, data: RiskItemUpdate) -> RiskItem:
        return await self.risk_item_repo.update(item, data)

    async def delete_risk_item(self, item: RiskItem) -> None:
        await self.risk_item_repo.delete(item)

    # ── Mitigation actions CRUD ───────────────────────────────────────────

    async def add_mitigation(self, job: Job, data: MitigationActionCreate) -> MitigationAction:
        return await self.mitigation_repo.add(job.id, data)

    async def update_mitigation(self, action: MitigationAction, data: MitigationActionUpdate) -> MitigationAction:
        return await self.mitigation_repo.update(action, data)

    async def delete_mitigation(self, action: MitigationAction) -> None:
        await self.mitigation_repo.delete(action)

    # ── Private helpers ───────────────────────────────────────────────────

    @staticmethod
    def _resolve_language(job: Job, interface_language: str) -> str:
        """Pick the AI output language based on the offer's content.

        The candidate-facing fields drive the decision: if the offer was
        written in Polish we want a Polish analysis even when the recruiter's
        UI is in English. Falls back to ``interface_language`` when the
        content is empty or doesn't carry strong Polish signals.
        """
        sample = " ".join(
            filter(
                None,
                (
                    job.title,
                    job.role_summary,
                    job.role_purpose,
                    job.responsibilities,
                    job.must_haves,
                    job.value_proposition,
                    job.benefits,
                ),
            )
        )
        return detect_text_language(sample, fallback=interface_language)

    @staticmethod
    def _merged_state(job: Job, data: JobUpdate) -> dict[str, Any]:
        """Snapshot current job columns + apply update payload.

        Used only for status-transition validation — `PublishValidator` needs
        the post-update state to decide if draft→open is allowed.
        """
        snapshot = {c.name: getattr(job, c.name) for c in Job.__table__.columns}
        snapshot.update(data.model_dump(exclude_unset=True))
        return snapshot

    @staticmethod
    def _job_to_dict(job: Job, fields: tuple[str, ...]) -> dict[str, Any]:
        """Project selected Job attributes to a JSON-friendly dict.

        Stringifies StrEnum values so the LLM payload is clean JSON.
        """
        result: dict[str, Any] = {}
        for field in fields:
            value = getattr(job, field, None)
            if value is not None and hasattr(value, "value"):  # StrEnum / Enum
                value = str(value)
            result[field] = value
        return result

    @staticmethod
    def _llm_or_fail(result: dict[str, Any], error_key: str) -> dict[str, Any]:
        """Strip ``_meta`` and ensure the LLM returned a non-empty result."""
        result.pop("_meta", None)
        if not result:
            raise UnprocessableError(t(error_key))
        return result
