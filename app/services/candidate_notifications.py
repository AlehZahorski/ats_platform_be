from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.automation.repository import AutomationRepository
from app.modules.email_templates.service import EmailTemplateService
from app.services.mailer import mail_service


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
) -> bool:
    repo = AutomationRepository(db)
    rules = await repo.get_matching_rules(
        company_id=company_id,
        trigger_type="stage_changed",
        trigger_value=str(stage_id),
    )

    if rules:
        rule = rules[0]
        if rule.template:
            template_service = EmailTemplateService(db)
            subject, body = await template_service.render_for_send(
                rule.template,
                {
                    "candidate_name": candidate_name,
                    "candidate_email": candidate_email,
                    "job_title": job_title,
                    "company_name": company_name,
                    "stage_name": stage_name,
                    "tracking_url": tracking_url,
                    "interview_date": interview_at.isoformat() if interview_at else "",
                    "interview_url": interview_url or "",
                    "interview_notes": interview_notes or "",
                    "interview_duration": interview_duration_minutes or "",
                },
            )
            mail_service.send_html(background_tasks, candidate_email, subject, body)
            return True

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
        return False

    mail_service.send_status_change(
        background_tasks,
        to_email=candidate_email,
        candidate_name=candidate_name,
        job_title=job_title,
        new_stage=stage_name,
        tracking_url=tracking_url,
    )
    return False
