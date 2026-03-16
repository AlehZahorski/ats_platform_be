from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import generate_public_token
from app.modules.applications.models import Application, ApplicationAnswer, CandidateScore
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
    ) -> Application:
        app = Application(
            job_id=job_id,
            first_name=data.first_name,
            last_name=data.last_name,
            email=data.email,
            phone=data.phone,
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
                selectinload(Application.stage_history).selectinload(
                    Application.stage_history.property.mapper.class_.stage
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
            )
        )
        return result.scalar_one_or_none()