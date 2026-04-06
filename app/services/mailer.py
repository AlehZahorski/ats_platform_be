from __future__ import annotations

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from datetime import datetime

from fastapi import BackgroundTasks
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.config import settings

# ---------------------------------------------------------------------------
# Jinja2 template environment
# ---------------------------------------------------------------------------
_TEMPLATE_DIR = Path(__file__).parent.parent.parent / "templates" / "email"

_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html"]),
)


def _render_template(template_name: str, context: dict) -> str:
    template = _jinja_env.get_template(template_name)
    return template.render(**context)


# ---------------------------------------------------------------------------
# Low-level SMTP send (runs in background thread)
# ---------------------------------------------------------------------------
def _send_smtp(to_email: str, subject: str, html_body: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    msg["To"] = to_email

    msg.attach(MIMEText(html_body, "html"))

    context = ssl.create_default_context()

    if settings.smtp_tls:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.ehlo()
            server.starttls(context=context)
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.smtp_from_email, to_email, msg.as_string())
    else:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=context) as server:
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.smtp_from_email, to_email, msg.as_string())


# ---------------------------------------------------------------------------
# Public mail service
# ---------------------------------------------------------------------------
class MailService:
    """
    High-level mail service.  All public methods enqueue an async background
    task so the HTTP response is never blocked by SMTP.
    """

    def _enqueue(
        self,
        background_tasks: BackgroundTasks,
        to_email: str,
        subject: str,
        html: str,
    ) -> None:
        background_tasks.add_task(_send_smtp, to_email, subject, html)

    def send_html(
        self,
        background_tasks: BackgroundTasks,
        to_email: str,
        subject: str,
        html_body: str,
    ) -> None:
        self._enqueue(background_tasks, to_email, subject, html_body)

    # ------------------------------------------------------------------
    # Email verification
    # ------------------------------------------------------------------
    def send_verification_email(
        self,
        background_tasks: BackgroundTasks,
        to_email: str,
        verification_url: str,
    ) -> None:
        html = _render_template(
            "verification.html",
            {"verification_url": verification_url, "app_name": settings.app_name},
        )
        self._enqueue(background_tasks, to_email, "Verify your email address", html)

    # ------------------------------------------------------------------
    # Password reset
    # ------------------------------------------------------------------
    def send_password_reset(
        self,
        background_tasks: BackgroundTasks,
        to_email: str,
        reset_url: str,
    ) -> None:
        html = _render_template(
            "password_reset.html",
            {"reset_url": reset_url, "app_name": settings.app_name},
        )
        self._enqueue(background_tasks, to_email, "Reset your password", html)

    # ------------------------------------------------------------------
    # Candidate application confirmation + tracking link
    # ------------------------------------------------------------------
    def send_application_confirmation(
        self,
        background_tasks: BackgroundTasks,
        to_email: str,
        candidate_name: str,
        job_title: str,
        tracking_url: str,
    ) -> None:
        html = _render_template(
            "application_confirmation.html",
            {
                "candidate_name": candidate_name,
                "job_title": job_title,
                "tracking_url": tracking_url,
                "app_name": settings.app_name,
            },
        )
        self._enqueue(
            background_tasks,
            to_email,
            f"Your application for {job_title} has been received",
            html,
        )

    # ------------------------------------------------------------------
    # Status change notification
    # ------------------------------------------------------------------
    def send_status_change(
        self,
        background_tasks: BackgroundTasks,
        to_email: str,
        candidate_name: str,
        job_title: str,
        new_stage: str,
        tracking_url: str,
    ) -> None:
        html = _render_template(
            "status_change.html",
            {
                "candidate_name": candidate_name,
                "job_title": job_title,
                "new_stage": new_stage,
                "tracking_url": tracking_url,
                "app_name": settings.app_name,
            },
        )
        self._enqueue(
            background_tasks,
            to_email,
            f"Update on your application for {job_title}",
            html,
        )

    def send_interview_stage_update(
        self,
        background_tasks: BackgroundTasks,
        to_email: str,
        candidate_name: str,
        job_title: str,
        tracking_url: str,
        interview_at: datetime,
        meeting_url: str,
        duration_minutes: int | None = None,
        notes: str | None = None,
    ) -> None:
        interview_date = interview_at.strftime("%Y-%m-%d")
        interview_time = interview_at.strftime("%H:%M")
        html = _render_template(
            "interview_stage_update.html",
            {
                "candidate_name": candidate_name,
                "job_title": job_title,
                "tracking_url": tracking_url,
                "interview_date": interview_date,
                "interview_time": interview_time,
                "interview_url": meeting_url,
                "duration_minutes": duration_minutes,
                "notes": notes,
                "app_name": settings.app_name,
            },
        )
        self._enqueue(
            background_tasks,
            to_email,
            f"Interview details for your application to {job_title}",
            html,
        )


mail_service = MailService()
