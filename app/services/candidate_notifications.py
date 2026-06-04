from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.mailer import mail_service


class CandidateNotificationService:
    """Default candidate notification emails for pipeline stage changes.

    Faza 3: automation-RULE emails are now handled by AutomationService.trigger
    (which also records an `email_sent` ApplicationEvent + `automation_triggered`
    AuditLog). This service only sends the FALLBACK notification used when no
    automation rule matched the stage — either the interview-update email or the
    plain status-change email.
    """

    def __init__(self, db: AsyncSession) -> None:
        # db kept for call-site compatibility; no longer used directly here.
        self._db = db

    async def send_stage_change(
        self,
        *,
        background_tasks: BackgroundTasks,
        company_id: uuid.UUID,
        stage_id: uuid.UUID,
        candidate_email: str,
        candidate_name: str,
        job_title: str,
        stage_name: str,
        tracking_url: str,
        company_name: str,
        interview_at: datetime | None = None,
        interview_url: str | None = None,
        interview_notes: str | None = None,
        interview_duration_minutes: int | None = None,
    ) -> None:
        if stage_name.strip().lower() == "interview" and interview_at and interview_url:
            mail_service.send_interview_stage_update(
                background_tasks,
                to_email=candidate_email,
                candidate_name=candidate_name,
                job_title=job_title,
                tracking_url=tracking_url,
                interview_at=interview_at,
                meeting_url=interview_url,
                duration_minutes=interview_duration_minutes,
                notes=interview_notes,
            )
            return

        mail_service.send_status_change(
            background_tasks,
            to_email=candidate_email,
            candidate_name=candidate_name,
            job_title=job_title,
            new_stage=stage_name,
            tracking_url=tracking_url,
        )


async def send_stage_change_notification(
    *,
    db: AsyncSession,
    background_tasks: BackgroundTasks,
    company_id: uuid.UUID,
    stage_id: uuid.UUID,
    candidate_email: str,
    candidate_name: str,
    job_title: str,
    stage_name: str,
    tracking_url: str,
    company_name: str,
    interview_at: datetime | None = None,
    interview_url: str | None = None,
    interview_notes: str | None = None,
    interview_duration_minutes: int | None = None,
) -> None:
    """Module-level entry point kept for the pipeline router. Sends the default
    (non-automation) stage-change notification."""
    service = CandidateNotificationService(db)
    await service.send_stage_change(
        background_tasks=background_tasks,
        company_id=company_id,
        stage_id=stage_id,
        candidate_email=candidate_email,
        candidate_name=candidate_name,
        job_title=job_title,
        stage_name=stage_name,
        tracking_url=tracking_url,
        company_name=company_name,
        interview_at=interview_at,
        interview_url=interview_url,
        interview_notes=interview_notes,
        interview_duration_minutes=interview_duration_minutes,
    )
