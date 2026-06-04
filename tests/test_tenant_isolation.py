"""Tenant-isolation (IDOR) regression tests — Faza 1 (plan-naprawy).

Company B must never read or mutate Company A's application-scoped resources by
supplying A's ids. Every protected ``{application_id}`` / ``{interview_id}``
endpoint must return 404 (not 200, not 403) for a cross-tenant id — a 403 would
already leak that the id exists in another tenant.

Also covers the Google OAuth ``state`` (CSRF) check.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from app.core.security import create_access_token
from app.modules.interviews.models import Interview
from tests.helpers import (
    create_application,
    create_company,
    create_job,
    create_pipeline_stages,
    create_verified_user,
)


def _token(user_id: uuid.UUID, company_id: uuid.UUID) -> str:
    return create_access_token(str(user_id), {"company_id": str(company_id), "role": "owner"})


async def _setup(db_session):
    """Company A owns an application + interview; return ids and Company B's token."""
    comp_a = await create_company(db_session, "Tenant A")
    await create_verified_user(db_session, comp_a.id, "owner-a@a.test")
    await create_pipeline_stages(db_session)
    job_a = await create_job(db_session, comp_a.id, "Role A", "open")
    app_a = await create_application(db_session, job_a.id, email="cand-a@a.test")

    interview_a = Interview(
        application_id=app_a.id,
        scheduled_at=datetime(2030, 1, 1, 12, 0, tzinfo=UTC),
        meeting_url="https://meet.example/a",
        status="scheduled",
    )
    db_session.add(interview_a)
    await db_session.flush()

    comp_b = await create_company(db_session, "Tenant B")
    user_b = await create_verified_user(db_session, comp_b.id, "owner-b@b.test")
    await db_session.commit()

    return app_a, interview_a, _token(user_b.id, comp_b.id)


@pytest.mark.asyncio
async def test_cross_tenant_application_endpoints_return_404(
    client: AsyncClient, db_session
) -> None:
    app_a, _interview_a, token_b = await _setup(db_session)
    client.cookies.clear()
    client.cookies.set("access_token", token_b)

    aid = str(app_a.id)
    rnd = str(uuid.uuid4())
    # (method, path, json-body-or-None). Bodies are schema-valid so the request
    # reaches the ownership guard (not a 422) — the guard is what must 404.
    cases: list[tuple[str, str, dict | None]] = [
        ("GET", f"/api/v1/applications/{aid}", None),
        ("GET", f"/api/v1/applications/{aid}/cv-parse", None),
        ("POST", f"/api/v1/applications/{aid}/cv-parse/retry", None),
        ("GET", f"/api/v1/applications/{aid}/matches", None),
        (
            "POST",
            f"/api/v1/applications/{aid}/score",
            {"communication": 3, "technical": 3, "culture_fit": 3},
        ),
        ("POST", f"/api/v1/notes/applications/{aid}/notes", {"content": "leak"}),
        ("GET", f"/api/v1/notes/applications/{aid}/notes", None),
        ("POST", f"/api/v1/tags/applications/{aid}/tags", {"tag_id": rnd}),
        ("DELETE", f"/api/v1/tags/applications/{aid}/tags/{rnd}", None),
        ("GET", f"/api/v1/tags/applications/{aid}/tags", None),
        (
            "POST",
            f"/api/v1/interviews/applications/{aid}/interviews",
            {"scheduled_at": "2030-01-01T10:00:00Z", "meeting_url": "https://x.test"},
        ),
        ("GET", f"/api/v1/interviews/applications/{aid}/interviews", None),
        ("GET", f"/api/v1/pipeline/applications/{aid}/history", None),
        (
            "POST",
            f"/api/v1/gdpr/applications/{aid}/consents",
            {"consent_id": rnd, "accepted": True},
        ),
        ("GET", f"/api/v1/gdpr/applications/{aid}/consents", None),
    ]

    leaks = []
    for method, path, body in cases:
        kwargs = {"json": body} if body is not None else {}
        resp = await client.request(method, path, **kwargs)
        if resp.status_code != 404:
            leaks.append(f"{method} {path} -> {resp.status_code}")

    assert not leaks, "cross-tenant access leaked on: " + "; ".join(leaks)


@pytest.mark.asyncio
async def test_cross_tenant_interview_mutations_return_404(
    client: AsyncClient, db_session
) -> None:
    _app_a, interview_a, token_b = await _setup(db_session)
    client.cookies.clear()
    client.cookies.set("access_token", token_b)

    iid = str(interview_a.id)
    patch = await client.patch(f"/api/v1/interviews/interviews/{iid}", json={"notes": "hax"})
    assert patch.status_code == 404
    delete = await client.delete(f"/api/v1/interviews/interviews/{iid}")
    assert delete.status_code == 404


@pytest.mark.asyncio
async def test_owner_can_access_own_application(client: AsyncClient, db_session) -> None:
    """Sanity: the legitimate owner is NOT blocked by the new guard."""
    comp = await create_company(db_session, "Owner Co")
    user = await create_verified_user(db_session, comp.id, "owner@own.test")
    await create_pipeline_stages(db_session)
    job = await create_job(db_session, comp.id, "Role", "open")
    app = await create_application(db_session, job.id, email="cand@own.test")
    await db_session.commit()

    client.cookies.clear()
    client.cookies.set("access_token", _token(user.id, comp.id))
    resp = await client.get(f"/api/v1/applications/{app.id}")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_cross_tenant_body_param_links_return_404(
    client: AsyncClient, db_session
) -> None:
    """Body-param resource ids (template_id / application_id) must also be
    company-scoped, so B can't link its own job/task/rule to A's resource."""
    from app.modules.email_templates.models import EmailTemplate
    from app.modules.forms.models import FormTemplate

    comp_a = await create_company(db_session, "Body A")
    await create_verified_user(db_session, comp_a.id, "a@body.test")
    await create_pipeline_stages(db_session)
    job_a = await create_job(db_session, comp_a.id, "Role A", "open")
    app_a = await create_application(db_session, job_a.id, email="c@body.test")
    form_a = FormTemplate(company_id=comp_a.id, name="Form A")
    email_a = EmailTemplate(
        company_id=comp_a.id, name="Mail A", type="custom", subject="s", body="b", language="en"
    )
    db_session.add_all([form_a, email_a])
    await db_session.flush()

    comp_b = await create_company(db_session, "Body B")
    user_b = await create_verified_user(db_session, comp_b.id, "b@body.test")
    job_b = await create_job(db_session, comp_b.id, "Role B", "open")
    await db_session.commit()

    client.cookies.clear()
    client.cookies.set("access_token", _token(user_b.id, comp_b.id))

    # B links its own job to A's form template
    r1 = await client.put(
        f"/api/v1/jobs/{job_b.id}/template", json={"template_id": str(form_a.id)}
    )
    assert r1.status_code == 404, f"jobs/template leaked: {r1.status_code}"

    # B creates a task pointing at A's application
    r2 = await client.post(
        "/api/v1/tasks", json={"title": "x", "application_id": str(app_a.id)}
    )
    assert r2.status_code == 404, f"tasks leaked: {r2.status_code}"

    # B creates an automation rule referencing A's email template
    r3 = await client.post(
        "/api/v1/automations",
        json={"name": "r", "trigger_type": "stage_changed", "template_id": str(email_a.id)},
    )
    assert r3.status_code == 404, f"automations leaked: {r3.status_code}"


@pytest.mark.asyncio
async def test_google_callback_rejects_missing_state(client: AsyncClient, db_session) -> None:
    client.cookies.clear()
    resp = await client.get("/api/v1/auth/google/callback", params={"code": "x", "state": "abc"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_google_callback_rejects_mismatched_state(client: AsyncClient, db_session) -> None:
    client.cookies.clear()
    client.cookies.set("oauth_state", "issued-value")
    resp = await client.get(
        "/api/v1/auth/google/callback", params={"code": "x", "state": "attacker-value"}
    )
    assert resp.status_code == 401
