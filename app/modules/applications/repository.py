from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import generate_public_token
from app.modules.applications.models import (
    Application,
    ApplicationAnswer,
    ApplicationDuplicateLink,
    CVParseJob,
    CandidateProfile,
    CandidateScore,
)
from app.modules.applications.schemas import ApplicationCreate, ScoreCreate
from app.modules.pipeline.models import ApplicationStageHistory


class ApplicationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

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
            self.db.add(
                ApplicationAnswer(
                    application_id=app.id,
                    field_id=answer.field_id,
                    value=answer.value,
                )
            )
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
                selectinload(Application.stage_history).selectinload(
                    ApplicationStageHistory.stage
                ),
            )
        )
        return result.scalar_one_or_none()

    async def list(
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

        count_result = await self.db.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = count_result.scalar_one()

        result = await self.db.execute(
            query.offset(skip).limit(limit).order_by(Application.created_at.desc())
        )
        return list(result.scalars().all()), total

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
        for duplicate_application_id in duplicate_application_ids:
            self.db.add(
                ApplicationDuplicateLink(
                    source_application_id=source_application_id,
                    duplicate_application_id=duplicate_application_id,
                    match_reasons=match_reasons.get(duplicate_application_id, []),
                )
            )
        await self.db.flush()

    async def _load(self, application_id: uuid.UUID) -> Application | None:
        result = await self.db.execute(
            select(Application)
            .where(Application.id == application_id)
            .options(
                selectinload(Application.stage),
                selectinload(Application.answers).selectinload(
                    ApplicationAnswer.field
                ),
                selectinload(Application.stage_history).selectinload(
                    ApplicationStageHistory.stage
                ),
                selectinload(Application.scores),
                selectinload(Application.tag_links),
                selectinload(Application.cv_parse_jobs),
                selectinload(Application.candidate_profile),
            )
        )
        return result.scalar_one_or_none()

    async def create_cv_parse_job(self, application_id: uuid.UUID, cv_url: str | None) -> CVParseJob:
        job = CVParseJob(application_id=application_id, cv_url=cv_url, status="queued")
        self.db.add(job)
        await self.db.flush()
        await self.db.refresh(job)
        return job

    async def get_cv_parse_job(self, parse_job_id: uuid.UUID) -> CVParseJob | None:
        result = await self.db.execute(
            select(CVParseJob).where(CVParseJob.id == parse_job_id).options(selectinload(CVParseJob.application))
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
        if latest and latest.status in {"queued", "extracting", "parsing"}:
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
        parsing_status: str,
        parsing_error: str | None = None,
        last_parsed_at=None,
    ) -> CandidateProfile:
        result = await self.db.execute(
            select(CandidateProfile).where(CandidateProfile.application_id == application_id)
        )
        profile = result.scalar_one_or_none()
        if profile:
            profile.headline = headline
            profile.summary = summary
            profile.skills = skills
            profile.experience = experience
            profile.education = education
            profile.parsing_status = parsing_status
            profile.parsing_error = parsing_error
            profile.last_parsed_at = last_parsed_at
        else:
            profile = CandidateProfile(
                application_id=application_id,
                headline=headline,
                summary=summary,
                skills=skills,
                experience=experience,
                education=education,
                parsing_status=parsing_status,
                parsing_error=parsing_error,
                last_parsed_at=last_parsed_at,
            )
            self.db.add(profile)
        await self.db.flush()
        await self.db.refresh(profile)
        return profile
