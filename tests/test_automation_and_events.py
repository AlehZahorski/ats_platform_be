"""Faza 3 (plan-naprawy) — automation wiring, activity timeline, GDPR export.

- automation rules now fire on stage_changed + application_created, recording an
  `email_sent` ApplicationEvent + `automation_triggered` AuditLog,
- GET /applications/{id}/events exposes the (previously write-only) timeline,
- GET /gdpr/applications/{id}/export returns the candidate's personal data.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import BackgroundTasks
from httpx import AsyncClient
from sqlalchemy import select

from app.core.enums.automation import AutomationTriggerType
from app.core.security import create_access_token
from app.modules.application_events.models import ApplicationEvent
from app.modules.audit.models import AuditLog
from app.modules.automation.models import AutomationRule
from app.modules.automation.repository import AutomationRepository
from app.modules.automation.schemas import AutomationTriggerPayload
from app.modules.automation.service import AutomationService
from app.modules.email_templates.models import EmailTemplate
from app.services.mailer import mail_service
from tests.helpers import (
    create_application,
    create_company,
    create_job,
    create_pipeline_stages,
    create_verified_user,
)


@pytest.fixture(autouse=True)
def _disable_email_sending(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "send_application_confirmation",
        "send_status_change",
        "send_interview_stage_update",
        "send_html",
    ):
        monkeypatch.setattr(mail_service, name, lambda *a, **k: None)


def _token(user_id: uuid.UUID, company_id: uuid.UUID) -> str:
    return create_access_token(str(user_id), {"company_id": str(company_id), "role": "owner"})


async def _email_template(db, company_id: uuid.UUID) -> EmailTemplate:
    tpl = EmailTemplate(
        company_id=company_id,
        name="Ack",
        type="custom",
        subject="Hi {{candidate_name}}",
        body="Thanks for applying, {{candidate_name}}.",
        language="en",
    )
    db.add(tpl)
    await db.flush()
    return tpl


# ── automation: stage_changed ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stage_change_with_rule_records_email_event_and_audit(
    client: AsyncClient, db_session
) -> None:
    comp = await create_company(db_session, "Auto Co")
    user = await create_verified_user(db_session, comp.id, "hr@example.com")
    stages = await create_pipeline_stages(db_session)
    target = stages[1]  # "Screening" — non-interview, no meeting link required
    job = await create_job(db_session, comp.id, "Role", "open")
    app = await create_application(db_session, job.id, stage_id=stages[0].id)
    tpl = await _email_template(db_session, comp.id)
    db_session.add(
        AutomationRule(
            company_id=comp.id,
            name="Screening ack",
            trigger_type="stage_changed",
            trigger_value=str(target.id),
            template_id=tpl.id,
            is_active=True,
        )
    )
    await db_session.commit()

    client.cookies.set("access_token", _token(user.id, comp.id))
    resp = await client.patch(
        f"/api/v1/pipeline/applications/{app.id}/stage",
        json={"stage_id": str(target.id), "notify_candidate": True},
    )
    assert resp.status_code == 200

    events = (
        await db_session.execute(
            select(ApplicationEvent).where(
                ApplicationEvent.application_id == app.id,
                ApplicationEvent.event_type == "email_sent",
            )
        )
    ).scalars().all()
    assert len(events) == 1

    audits = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.entity_id == app.id, AuditLog.action == "automation_triggered"
            )
        )
    ).scalars().all()
    assert len(audits) == 1


# ── automation: application_created (via the public apply endpoint) ───────────


@pytest.mark.asyncio
async def test_apply_fires_application_created_rule(client: AsyncClient, db_session) -> None:
    comp = await create_company(db_session, "Apply Auto Co")
    await create_verified_user(db_session, comp.id, "hr2@example.com")
    await create_pipeline_stages(db_session)
    job = await create_job(db_session, comp.id, "Role", "open")
    tpl = await _email_template(db_session, comp.id)
    db_session.add(
        AutomationRule(
            company_id=comp.id,
            name="Auto-ack",
            trigger_type="application_created",
            trigger_value=None,
            template_id=tpl.id,
            is_active=True,
        )
    )
    await db_session.commit()

    client.cookies.clear()
    resp = await client.post(
        f"/api/v1/applications/apply/{job.id}",
        data={"first_name": "A", "last_name": "B", "email": "applicant@example.com"},
    )
    assert resp.status_code == 201
    app_id = resp.json()["id"]

    events = (
        await db_session.execute(
            select(ApplicationEvent).where(
                ApplicationEvent.application_id == uuid.UUID(app_id),
                ApplicationEvent.event_type == "email_sent",
            )
        )
    ).scalars().all()
    assert len(events) == 1


@pytest.mark.asyncio
async def test_trigger_returns_false_when_no_rule(db_session) -> None:
    comp = await create_company(db_session, "No Rule Co")
    job = await create_job(db_session, comp.id, "Role", "open")
    app = await create_application(db_session, job.id, email="x@example.com")
    await db_session.flush()

    svc = AutomationService(AutomationRepository(db_session))
    fired = await svc.trigger(
        AutomationTriggerPayload(
            trigger_type=AutomationTriggerType.application_created,
            trigger_value=None,
            application_id=app.id,
            company_id=comp.id,
            variables={},
        ),
        BackgroundTasks(),
        "x@example.com",
    )
    assert fired is False


# ── activity timeline endpoint ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_events_endpoint_returns_timeline(client: AsyncClient, db_session) -> None:
    comp = await create_company(db_session, "Timeline Co")
    user = await create_verified_user(db_session, comp.id, "hr3@example.com")
    await create_pipeline_stages(db_session)
    job = await create_job(db_session, comp.id, "Role", "open")
    app = await create_application(db_session, job.id, email="cand@example.com")
    await db_session.commit()

    client.cookies.set("access_token", _token(user.id, comp.id))
    # Scheduling an interview writes an `interview_scheduled` ApplicationEvent.
    iv = await client.post(
        f"/api/v1/interviews/applications/{app.id}/interviews",
        json={"scheduled_at": "2030-01-01T10:00:00Z", "meeting_url": "https://x.example"},
    )
    assert iv.status_code == 201

    events = await client.get(f"/api/v1/applications/{app.id}/events")
    assert events.status_code == 200
    types = [e["event_type"] for e in events.json()]
    assert "interview_scheduled" in types


@pytest.mark.asyncio
async def test_events_endpoint_cross_tenant_404(client: AsyncClient, db_session) -> None:
    comp_a = await create_company(db_session, "T A")
    await create_verified_user(db_session, comp_a.id, "a@example.com")
    job_a = await create_job(db_session, comp_a.id, "Role", "open")
    app_a = await create_application(db_session, job_a.id, email="a-cand@example.com")
    comp_b = await create_company(db_session, "T B")
    user_b = await create_verified_user(db_session, comp_b.id, "b@example.com")
    await db_session.commit()

    client.cookies.set("access_token", _token(user_b.id, comp_b.id))
    resp = await client.get(f"/api/v1/applications/{app_a.id}/events")
    assert resp.status_code == 404


# ── GDPR export ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_gdpr_export_returns_personal_data(client: AsyncClient, db_session) -> None:
    comp = await create_company(db_session, "Export Co")
    user = await create_verified_user(db_session, comp.id, "hr4@example.com")
    job = await create_job(db_session, comp.id, "Role", "open")
    app = await create_application(db_session, job.id, email="exportme@example.com")
    await db_session.commit()

    client.cookies.set("access_token", _token(user.id, comp.id))
    note = await client.post(
        f"/api/v1/notes/applications/{app.id}/notes",
        json={"content": "Strong candidate"},
    )
    assert note.status_code == 201

    resp = await client.get(f"/api/v1/gdpr/applications/{app.id}/export")
    assert resp.status_code == 200
    data = resp.json()
    assert data["application"]["email"] == "exportme@example.com"
    assert any(n["content"] == "Strong candidate" for n in data["notes"])
    assert "stage_history" in data and "events" in data and "consents" in data


@pytest.mark.asyncio
async def test_gdpr_export_cross_tenant_404(client: AsyncClient, db_session) -> None:
    comp_a = await create_company(db_session, "EX A")
    await create_verified_user(db_session, comp_a.id, "exa@example.com")
    job_a = await create_job(db_session, comp_a.id, "Role", "open")
    app_a = await create_application(db_session, job_a.id, email="exa-cand@example.com")
    comp_b = await create_company(db_session, "EX B")
    user_b = await create_verified_user(db_session, comp_b.id, "exb@example.com")
    await db_session.commit()

    client.cookies.set("access_token", _token(user_b.id, comp_b.id))
    resp = await client.get(f"/api/v1/gdpr/applications/{app_a.id}/export")
    assert resp.status_code == 404
