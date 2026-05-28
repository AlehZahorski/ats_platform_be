from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base_repository import BaseRepository
from app.core.enums.applications import CVParseStatus, ParsingStatus
from app.core.security import generate_public_token
from app.modules.applications.models import (
    ApiUsageLog,
    Application,
    ApplicationAnswer,
    ApplicationDuplicateLink,
    CVParseJob,
    CandidateJobMatch,
    CandidateProfile,
    CandidateScore,
)
from app.modules.applications.schemas import ApplicationCreate, ScoreCreate
from app.modules.pipeline.models import ApplicationStageHistory


class ApplicationRepository(BaseRepository[Application]):
    model = Application

    async def create(
        self,
        job_id: uuid.UUID,
        data: ApplicationCreate,
        cv_url: str | None,
        initial_stage_id: uuid.UUID | None,
        normalized_email: str,
        normalized_phone: str | None,
    ) -> Application:
        app = Application(
            job_id=job_id,
            first_name=data.first_name,
            last_name=data.last_name,
            email=data.email,
            normalized_email=normalized_email,
            phone=data.phone,
            normalized_phone=normalized_phone,
            cv_url=cv_url,
            stage_id=initial_stage_id,
            public_token=generate_public_token(),
        )
        self.db.add(app)
        await self.db.flush()

        for answer in data.answers:
            self.db.add(ApplicationAnswer(
                application_id=app.id,
                field_id=answer.field_id,
                value=answer.value,
            ))
        await self.db.flush()
        return await self._load(app.id)

    async def get_by_id(self, application_id: uuid.UUID) -> Application | None:
        return await self._load(application_id)

    async def get_by_token(self, token: str) -> Application | None:
        result = await self.db.execute(
            select(Application)
            .where(Application.public_token == token)
            .options(
                selectinload(Application.stage),
                selectinload(Application.job),
                selectinload(Application.stage_history).selectinload(ApplicationStageHistory.stage),
            )
        )
        return result.scalar_one_or_none()

    async def list_by_company(
        self,
        company_id: uuid.UUID,
        job_id: uuid.UUID | None = None,
        stage_id: uuid.UUID | None = None,
        search: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[Application], int]:
        from app.modules.jobs.models import Job

        query = (
            select(Application)
            .join(Job, Application.job_id == Job.id)
            .where(Job.company_id == company_id)
            .options(selectinload(Application.stage))
        )
        if job_id:
            query = query.where(Application.job_id == job_id)
        if stage_id:
            query = query.where(Application.stage_id == stage_id)
        if search:
            term = f"%{search}%"
            query = query.where(
                Application.first_name.ilike(term)
                | Application.last_name.ilike(term)
                | Application.email.ilike(term)
            )

        total = (await self.db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
        items = (
            await self.db.execute(query.offset(skip).limit(limit).order_by(Application.created_at.desc()))
        ).scalars().all()
        return list(items), total

    async def upsert_score(
        self,
        application_id: uuid.UUID,
        recruiter_id: uuid.UUID,
        data: ScoreCreate,
    ) -> CandidateScore:
        result = await self.db.execute(
            select(CandidateScore).where(
                CandidateScore.application_id == application_id,
                CandidateScore.recruiter_id == recruiter_id,
            )
        )
        score = result.scalar_one_or_none()
        if score:
            score.communication = data.communication
            score.technical = data.technical
            score.culture_fit = data.culture_fit
        else:
            score = CandidateScore(
                application_id=application_id,
                recruiter_id=recruiter_id,
                **data.model_dump(),
            )
            self.db.add(score)
        await self.db.flush()
        await self.db.refresh(score)
        return score

    async def list_potential_duplicates(
        self,
        company_id: uuid.UUID,
        normalized_email: str,
        normalized_phone: str | None,
        limit: int = 10,
    ) -> list[Application]:
        from app.modules.jobs.models import Job

        conditions = [Application.normalized_email == normalized_email]
        if normalized_phone:
            conditions.append(Application.normalized_phone == normalized_phone)

        result = await self.db.execute(
            select(Application)
            .join(Job, Application.job_id == Job.id)
            .where(Job.company_id == company_id)
            .where(or_(*conditions))
            .options(selectinload(Application.stage), selectinload(Application.job))
            .order_by(Application.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def create_duplicate_links(
        self,
        source_application_id: uuid.UUID,
        duplicate_application_ids: list[uuid.UUID],
        match_reasons: dict[uuid.UUID, list[str]],
    ) -> None:
        for dup_id in duplicate_application_ids:
            self.db.add(ApplicationDuplicateLink(
                source_application_id=source_application_id,
                duplicate_application_id=dup_id,
                match_reasons=match_reasons.get(dup_id, []),
            ))
        await self.db.flush()

    async def create_cv_parse_job(self, application_id: uuid.UUID, cv_url: str | None, language: str = "en") -> CVParseJob:
        job = CVParseJob(application_id=application_id, cv_url=cv_url, status=CVParseStatus.queued, language=language)
        return await self.save(job)

    async def get_cv_parse_job(self, parse_job_id: uuid.UUID) -> CVParseJob | None:
        result = await self.db.execute(
            select(CVParseJob)
            .where(CVParseJob.id == parse_job_id)
            .options(selectinload(CVParseJob.application))
        )
        return result.scalar_one_or_none()

    async def get_latest_cv_parse_job(self, application_id: uuid.UUID) -> CVParseJob | None:
        result = await self.db.execute(
            select(CVParseJob)
            .where(CVParseJob.application_id == application_id)
            .order_by(CVParseJob.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create_or_replace_cv_parse_job(self, application_id: uuid.UUID, cv_url: str | None) -> CVParseJob:
        latest = await self.get_latest_cv_parse_job(application_id)
        if latest and latest.status in {CVParseStatus.queued, CVParseStatus.extracting, CVParseStatus.parsing}:
            return latest
        return await self.create_cv_parse_job(application_id, cv_url)

    async def upsert_candidate_profile(
        self,
        application_id: uuid.UUID,
        *,
        headline: str | None,
        summary: str | None,
        skills: list[dict],
        experience: list[dict],
        education: list[dict],
        parsing_status: ParsingStatus,
        parsing_error: str | None = None,
        last_parsed_at: datetime | None = None,
        parser_version: str = "v1-regex",
        # LLM enrichment fields (all optional)
        personal_summary: str | None = None,
        executive_summary: str | None = None,
        location: str | None = None,
        linkedin_url: str | None = None,
        github_url: str | None = None,
        technical_skills: list[dict] | None = None,
        soft_skills: list[dict] | None = None,
        languages: list[dict] | None = None,
        certifications: list[dict] | None = None,
        hobbies: list[str] | None = None,
        volunteering: list[str] | None = None,
        total_experience_years: float | None = None,
        seniority_estimate: str | None = None,
        strengths: list[str] | None = None,
        red_flags: list[str] | None = None,
        personality_signals: dict | None = None,
        evidence_quotes: list[dict] | None = None,
        culture_fit_notes: str | None = None,
    ) -> CandidateProfile:
        result = await self.db.execute(
            select(CandidateProfile).where(CandidateProfile.application_id == application_id)
        )
        profile = result.scalar_one_or_none()

        fields = dict(
            headline=headline,
            summary=summary,
            skills=skills,
            experience=experience,
            education=education,
            parsing_status=parsing_status,
            parsing_error=parsing_error,
            last_parsed_at=last_parsed_at,
            parser_version=parser_version,
            personal_summary=personal_summary,
            executive_summary=executive_summary,
            location=location,
            linkedin_url=linkedin_url,
            github_url=github_url,
            technical_skills=technical_skills,
            soft_skills=soft_skills,
            languages=languages,
            certifications=certifications,
            hobbies=hobbies,
            volunteering=volunteering,
            total_experience_years=total_experience_years,
            seniority_estimate=seniority_estimate,
            strengths=strengths,
            red_flags=red_flags,
            personality_signals=personality_signals,
            evidence_quotes=evidence_quotes,
            culture_fit_notes=culture_fit_notes,
        )

        if profile:
            for key, value in fields.items():
                setattr(profile, key, value)
        else:
            profile = CandidateProfile(application_id=application_id, **fields)
            self.db.add(profile)

        await self.db.flush()
        await self.db.refresh(profile)
        return profile

    async def save_job_match(
        self,
        application_id: uuid.UUID,
        candidate_profile_id: uuid.UUID,
        job_id: uuid.UUID,
        match_result: dict,
        *,
        match_key: str | None = None,
        match_status: str = "completed",
    ) -> CandidateJobMatch:
        match = CandidateJobMatch(
            application_id=application_id,
            candidate_profile_id=candidate_profile_id,
            job_id=job_id,
            match_score=match_result.get("match_score"),
            fit_score=match_result.get("fit_score"),
            reasoning=match_result.get("reasoning"),
            strengths_match=match_result.get("strengths_match"),
            gaps=match_result.get("gaps"),
            recommendation=match_result.get("recommendation"),
            llm_model=match_result.get("_meta", {}).get("model"),
            token_usage=match_result.get("_meta", {}).get("token_usage"),
            match_key=match_key,
            match_status=match_status,
        )
        self.db.add(match)
        await self.db.flush()
        await self.db.refresh(match)
        return match

    async def get_job_match_by_key(self, match_key: str) -> CandidateJobMatch | None:
        """F-09: idempotency lookup — returns the existing match for this
        candidate/job/profile snapshot, or None if we should call Claude."""
        result = await self.db.execute(
            select(CandidateJobMatch).where(CandidateJobMatch.match_key == match_key)
        )
        return result.scalar_one_or_none()

    async def get_job_matches(self, application_id: uuid.UUID) -> list[CandidateJobMatch]:
        result = await self.db.execute(
            select(CandidateJobMatch)
            .where(CandidateJobMatch.application_id == application_id)
            .order_by(CandidateJobMatch.created_at.desc())
        )
        return list(result.scalars().all())

    async def save_api_usage_log(
        self,
        company_id: uuid.UUID,
        operation: str,
        meta: dict,
        *,
        application_id: uuid.UUID | None = None,
    ) -> None:
        """Persist one LLM call's accounting data.

        F-20/F-22: ``meta`` now carries ``prompt_name``, ``prompt_version`` and
        ``correlation_id`` so the per-company dashboard can break down spend by
        prompt template version and a row can be traced back to its request.

        F-04 (audit_ai_ethics): ``application_id`` ties the call to the data
        subject (EU AI Act art. 12, RODO art. 30), and ``meta`` now also carries
        ``anthropic_request_id`` so we can correlate with Anthropic's logs.
        """
        token_usage = meta.get("token_usage", {})
        log = ApiUsageLog(
            company_id=company_id,
            operation=operation,
            llm_model=meta.get("model", ""),
            input_tokens=token_usage.get("input_tokens", 0),
            output_tokens=token_usage.get("output_tokens", 0),
            cost_usd=meta.get("cost_usd") or 0.0,
            prompt_name=meta.get("prompt_name"),
            prompt_version=meta.get("prompt_version"),
            correlation_id=meta.get("correlation_id"),
            application_id=application_id,
            anthropic_request_id=meta.get("anthropic_request_id"),
        )
        self.db.add(log)
        await self.db.flush()

    async def sum_llm_cost_last_24h(self, company_id: uuid.UUID) -> float:
        """F-05: rolling 24h cost used by the daily-budget guard."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        result = await self.db.execute(
            select(func.coalesce(func.sum(ApiUsageLog.cost_usd), 0.0)).where(
                ApiUsageLog.company_id == company_id,
                ApiUsageLog.created_at >= cutoff,
            )
        )
        return float(result.scalar_one() or 0.0)

    async def llm_usage_summary(
        self,
        company_id: uuid.UUID,
        *,
        days: int = 30,
    ) -> list[dict]:
        """F-17: per-day, per-model, per-prompt aggregation for the dashboard."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        day = func.date_trunc("day", ApiUsageLog.created_at)
        stmt = (
            select(
                day.label("day"),
                ApiUsageLog.llm_model,
                ApiUsageLog.prompt_name,
                func.count(ApiUsageLog.id).label("calls"),
                func.sum(ApiUsageLog.input_tokens).label("input_tokens"),
                func.sum(ApiUsageLog.output_tokens).label("output_tokens"),
                func.sum(ApiUsageLog.cost_usd).label("cost_usd"),
            )
            .where(
                ApiUsageLog.company_id == company_id,
                ApiUsageLog.created_at >= cutoff,
            )
            .group_by(day, ApiUsageLog.llm_model, ApiUsageLog.prompt_name)
            .order_by(day.desc())
        )
        result = await self.db.execute(stmt)
        return [
            {
                "day": row.day,
                "model": row.llm_model,
                "prompt_name": row.prompt_name,
                "calls": int(row.calls or 0),
                "input_tokens": int(row.input_tokens or 0),
                "output_tokens": int(row.output_tokens or 0),
                "cost_usd": float(row.cost_usd or 0.0),
            }
            for row in result.all()
        ]

    async def _load(self, application_id: uuid.UUID) -> Application | None:
        result = await self.db.execute(
            select(Application)
            .where(Application.id == application_id)
            .options(
                selectinload(Application.stage),
                selectinload(Application.answers).selectinload(ApplicationAnswer.field),
                selectinload(Application.stage_history).selectinload(ApplicationStageHistory.stage),
                selectinload(Application.scores),
                selectinload(Application.tag_links),
                selectinload(Application.cv_parse_jobs),
                selectinload(Application.candidate_profile),
            )
        )
        return result.scalar_one_or_none()
