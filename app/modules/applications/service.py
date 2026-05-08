from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field

from fastapi import BackgroundTasks, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base_service import BaseService
from app.core.enums.applications import BulkActionType, CVParseStatus, ParsingStatus
from app.core.exceptions import DuplicateDetectedError, NotFoundError, UnprocessableError
from app.modules.application_events.models import ApplicationEvent
from app.modules.applications.duplicate_service import (
    DuplicateCheckService,
    normalize_email,
    normalize_phone,
)
from app.modules.applications.models import Application, CVParseJob, CandidateScore
from app.modules.applications.repository import ApplicationRepository
from app.modules.applications.schemas import (
    AnswerInput,
    AnswerRead,
    ApplicationCreate,
    ApplicationList,
    ApplicationListItem,
    ApplicationRead,
    ApplicationTrackingRead,
    BulkAction,
    BulkResult,
    CVParseConfirmPayload,
    CVParseJobRead,
    CandidateProfileRead,
    DuplicateCheckRequest,
    DuplicateCheckResponse,
    ScoreCreate,
    ScoreRead,
    TrackingJobRead,
)
from app.modules.audit.models import AuditLog
from app.modules.audit.service import AuditService
from app.modules.pipeline.models import ApplicationStageHistory
from app.modules.pipeline.repository import PipelineRepository
from app.services.cv_parsing import run_cv_parse_job
from app.services.file_storage import file_storage
from app.services.mailer import mail_service


@dataclass
class ApplicationSubmitResult:
    application: Application
    parse_job: CVParseJob | None = None
    confirmation_email_sent: bool = False


class ApplicationService(BaseService[ApplicationRepository]):

    def __init__(
        self,
        repository: ApplicationRepository,
        pipeline_repo: PipelineRepository,
        audit: AuditService,
        duplicate_svc: DuplicateCheckService,
        db: AsyncSession,
    ) -> None:
        super().__init__(repository)
        self.pipeline_repo = pipeline_repo
        self.audit = audit
        self.duplicate_svc = duplicate_svc
        self.db = db

    # ------------------------------------------------------------------
    # Public: candidate submits application
    # ------------------------------------------------------------------
    async def submit_application(
        self,
        job_id: uuid.UUID,
        first_name: str,
        last_name: str,
        email: str,
        phone: str | None,
        raw_answers: str | None,
        cv_file: UploadFile | None,
        ignore_duplicate_warning: bool,
        background_tasks: BackgroundTasks,
        frontend_url: str,
    ) -> ApplicationSubmitResult:
        from app.modules.jobs.models import Job

        result = await self.db.execute(
            select(Job).where(Job.id == job_id, Job.status == "open")
        )
        job = result.scalar_one_or_none()
        if not job:
            raise NotFoundError("Job not found or not accepting applications.")

        duplicate_check = await self.duplicate_svc.check(
            company_id=job.company_id,
            email=email,
            phone=phone,
        )
        if duplicate_check.has_duplicates and not ignore_duplicate_warning:
            raise DuplicateDetectedError(duplicate_check)

        cv_url: str | None = None
        if cv_file and cv_file.filename:
            cv_url = await file_storage.save_cv(cv_file)

        stages = await self.pipeline_repo.list_stages()
        initial_stage_id = stages[0].id if stages else None

        parsed_answers = self._parse_answers(raw_answers)
        data = ApplicationCreate(
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            answers=parsed_answers,
        )
        application = await self.repository.create(
            job_id=job_id,
            data=data,
            cv_url=cv_url,
            initial_stage_id=initial_stage_id,
            normalized_email=normalize_email(email),
            normalized_phone=normalize_phone(phone),
        )

        parse_job: CVParseJob | None = None
        if cv_url:
            parse_job = await self.repository.create_cv_parse_job(application.id, cv_url)
            background_tasks.add_task(run_cv_parse_job, parse_job.id)

        if duplicate_check.has_duplicates:
            await self.repository.create_duplicate_links(
                source_application_id=application.id,
                duplicate_application_ids=[m.application_id for m in duplicate_check.matches],
                match_reasons={m.application_id: m.match_reasons for m in duplicate_check.matches},
            )

        tracking_url = f"{frontend_url}/track/{application.public_token}"
        mail_service.send_application_confirmation(
            background_tasks,
            to_email=email,
            candidate_name=f"{first_name} {last_name}",
            job_title=job.title,
            tracking_url=tracking_url,
        )

        return ApplicationSubmitResult(application=application, parse_job=parse_job)

    # ------------------------------------------------------------------
    # Public: duplicate pre-check
    # ------------------------------------------------------------------
    async def check_duplicate(self, data: DuplicateCheckRequest) -> DuplicateCheckResponse:
        from app.modules.jobs.models import Job

        result = await self.db.execute(
            select(Job).where(Job.id == data.job_id, Job.status == "open")
        )
        job = result.scalar_one_or_none()
        if not job:
            raise NotFoundError("Job not found or not accepting applications.")

        return await self.duplicate_svc.check(
            company_id=job.company_id,
            email=data.email,
            phone=data.phone,
        )

    # ------------------------------------------------------------------
    # Public: candidate tracks own application
    # ------------------------------------------------------------------
    async def track_application(self, token: str) -> ApplicationTrackingRead:
        application = await self.repository.get_by_token(token)
        if not application:
            raise NotFoundError("Application not found.")
        result = ApplicationTrackingRead.model_validate(application)
        if application.job:
            result.job = TrackingJobRead.model_validate(application.job)
        return result

    # ------------------------------------------------------------------
    # HR: list applications
    # ------------------------------------------------------------------
    async def list_applications(
        self,
        company_id: uuid.UUID,
        job_id: uuid.UUID | None,
        stage_id: uuid.UUID | None,
        search: str | None,
        skip: int,
        limit: int,
    ) -> ApplicationList:
        apps, total = await self.repository.list_by_company(
            company_id=company_id,
            job_id=job_id,
            stage_id=stage_id,
            search=search,
            skip=skip,
            limit=limit,
        )
        return ApplicationList(
            items=[ApplicationListItem.model_validate(a) for a in apps],
            total=total,
        )

    # ------------------------------------------------------------------
    # HR: single application detail
    # ------------------------------------------------------------------
    async def get_application_detail(self, application_id: uuid.UUID) -> ApplicationRead:
        application = await self.repository.get_by_id(application_id)
        if not application:
            raise NotFoundError("Application not found.")
        return self._build_application_read(application)

    # ------------------------------------------------------------------
    # HR: CV parsing
    # ------------------------------------------------------------------
    async def get_cv_parse_status(self, application_id: uuid.UUID) -> CVParseJobRead | None:
        parse_job = await self.repository.get_latest_cv_parse_job(application_id)
        if not parse_job:
            return None
        return CVParseJobRead.model_validate(parse_job)

    async def retry_cv_parse(
        self, application_id: uuid.UUID, background_tasks: BackgroundTasks
    ) -> CVParseJobRead:
        application = await self.repository.get_by_id(application_id)
        if not application:
            raise NotFoundError("Application not found.")
        if not application.cv_url:
            raise UnprocessableError("Application does not have a CV to parse.")
        parse_job = await self.repository.create_cv_parse_job(application_id, application.cv_url)
        background_tasks.add_task(run_cv_parse_job, parse_job.id)
        return CVParseJobRead.model_validate(parse_job)

    async def confirm_cv_parse(
        self, application_id: uuid.UUID, data: CVParseConfirmPayload
    ) -> ApplicationRead:
        application = await self.repository.get_by_id(application_id)
        if not application:
            raise NotFoundError("Application not found.")

        application.first_name = data.first_name
        application.last_name = data.last_name
        application.email = data.email
        application.normalized_email = normalize_email(data.email)
        application.phone = data.phone
        application.normalized_phone = normalize_phone(data.phone)

        latest_job = await self.repository.get_latest_cv_parse_job(application_id)
        if latest_job:
            latest_job.status = CVParseStatus.completed
            latest_job.completed_at = latest_job.completed_at or latest_job.updated_at
            latest_job.normalized_result = data.model_dump(mode="json")

        await self.repository.upsert_candidate_profile(
            application_id,
            headline=data.headline,
            summary=data.summary,
            skills=[item.model_dump() for item in data.skills],
            experience=[item.model_dump() for item in data.experience],
            education=[item.model_dump() for item in data.education],
            parsing_status=ParsingStatus.completed,
            parsing_error=None,
            last_parsed_at=latest_job.completed_at if latest_job else application.updated_at,
        )

        refreshed = await self.repository.get_by_id(application_id)
        return self._build_application_read(refreshed)

    # ------------------------------------------------------------------
    # HR: score
    # ------------------------------------------------------------------
    async def score_application(
        self, application_id: uuid.UUID, user_id: uuid.UUID, data: ScoreCreate
    ) -> ScoreRead:
        application = await self.repository.get_by_id(application_id)
        if not application:
            raise NotFoundError("Application not found.")
        score = await self.repository.upsert_score(application_id, user_id, data)
        return ScoreRead.model_validate(score)

    # ------------------------------------------------------------------
    # HR: bulk operations
    # ------------------------------------------------------------------
    async def bulk_action(
        self,
        data: BulkAction,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
        background_tasks: BackgroundTasks,
        frontend_url: str,
        company_name: str,
    ) -> BulkResult:
        from app.modules.jobs.models import Job
        from app.modules.interviews.repository import InterviewRepository
        from app.modules.pipeline.models import PipelineStage
        from app.modules.tags.models import ApplicationTag

        updated = 0
        failed = 0

        for app_id in data.application_ids:
            try:
                result = await self.db.execute(
                    select(Application)
                    .join(Job, Application.job_id == Job.id)
                    .where(Application.id == app_id, Job.company_id == company_id)
                )
                app = result.scalar_one_or_none()
                if not app:
                    failed += 1
                    continue

                if data.action == BulkActionType.stage_change:
                    stage_id = uuid.UUID(data.payload["stage_id"])
                    stage = await self.pipeline_repo.get_by_id(stage_id)
                    if not stage:
                        failed += 1
                        continue

                    interview = None
                    if stage.name.strip().lower() == "interview":
                        interview = await InterviewRepository(self.db).get_stage_ready_interview(app.id)
                        if not interview:
                            failed += 1
                            continue

                    app.stage_id = stage_id
                    self.db.add(ApplicationStageHistory(
                        application_id=app_id,
                        stage_id=stage_id,
                        changed_by=user_id,
                    ))

                    if data.payload.get("notify_candidate"):
                        from app.services.candidate_notifications import send_stage_change_notification
                        job_result = await self.db.execute(select(Job).where(Job.id == app.job_id))
                        job = job_result.scalar_one_or_none()
                        await send_stage_change_notification(
                            db=self.db,
                            background_tasks=background_tasks,
                            company_id=company_id,
                            stage_id=stage.id,
                            candidate_email=app.email,
                            candidate_name=f"{app.first_name} {app.last_name}",
                            job_title=job.title if job else "position",
                            stage_name=stage.name,
                            tracking_url=f"{frontend_url}/track/{app.public_token}",
                            company_name=company_name,
                            interview_at=interview.scheduled_at if interview else None,
                            interview_url=interview.meeting_url if interview else None,
                            interview_notes=interview.notes if interview else None,
                            interview_duration_minutes=interview.duration_minutes if interview else None,
                        )

                elif data.action == BulkActionType.reject:
                    res = await self.db.execute(
                        select(PipelineStage).where(func.lower(PipelineStage.name) == "rejected")
                    )
                    rejected_stage = res.scalar_one_or_none()
                    if rejected_stage:
                        app.stage_id = rejected_stage.id
                        self.db.add(ApplicationStageHistory(
                            application_id=app_id,
                            stage_id=rejected_stage.id,
                            changed_by=user_id,
                        ))

                        if data.payload.get("notify_candidate"):
                            from app.services.candidate_notifications import send_stage_change_notification
                            job_result = await self.db.execute(select(Job).where(Job.id == app.job_id))
                            job = job_result.scalar_one_or_none()
                            await send_stage_change_notification(
                                db=self.db,
                                background_tasks=background_tasks,
                                company_id=company_id,
                                stage_id=rejected_stage.id,
                                candidate_email=app.email,
                                candidate_name=f"{app.first_name} {app.last_name}",
                                job_title=job.title if job else "position",
                                stage_name=rejected_stage.name,
                                tracking_url=f"{frontend_url}/track/{app.public_token}",
                                company_name=company_name,
                            )

                elif data.action == BulkActionType.tag:
                    tag_id = uuid.UUID(data.payload["tag_id"])
                    existing = await self.db.execute(
                        select(ApplicationTag).where(
                            ApplicationTag.application_id == app_id,
                            ApplicationTag.tag_id == tag_id,
                        )
                    )
                    if not existing.scalar_one_or_none():
                        self.db.add(ApplicationTag(application_id=app_id, tag_id=tag_id))

                self.db.add(ApplicationEvent(
                    application_id=app_id,
                    company_id=company_id,
                    event_type="bulk_action",
                    event_value=data.action,
                    metadata_={"payload": data.payload, "user_id": str(user_id)},
                ))
                updated += 1

            except Exception:
                failed += 1
                continue

        self.db.add(AuditLog(
            company_id=company_id,
            user_id=user_id,
            action="bulk_action",
            entity_type="application",
            metadata_={"action": data.action, "count": updated, "ids": [str(i) for i in data.application_ids]},
        ))

        return BulkResult(updated=updated, failed=failed, action=data.action)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _build_application_read(application: Application) -> ApplicationRead:
        result = ApplicationRead.model_validate(application)
        result.answers = []
        for ans in (application.answers or []):
            answer = AnswerRead.model_validate(ans)
            if hasattr(ans, "field") and ans.field:
                answer.field_label = ans.field.label
                answer.field_type = ans.field.field_type
            result.answers.append(answer)
        if application.candidate_profile:
            result.candidate_profile = CandidateProfileRead.model_validate(application.candidate_profile)
        latest_parse_job = application.cv_parse_jobs[0] if application.cv_parse_jobs else None
        if latest_parse_job:
            result.latest_cv_parse_job = CVParseJobRead.model_validate(latest_parse_job)
        return result

    @staticmethod
    def _parse_answers(raw: str | None) -> list[AnswerInput]:
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
            return [
                AnswerInput(field_id=a["field_id"], value=a["value"])
                for a in parsed
                if a.get("field_id") and a.get("value") not in (None, "")
            ]
        except Exception:
            return []
