from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.core.security import create_access_token
from app.modules.interviews.models import Interview
from app.services.mailer import mail_service
from tests.helpers import (
    create_application,
    create_company,
    create_job,
    create_pipeline_stages,
    create_verified_user,
)


async def _get_authed_client(client, db_session, role: str = "recruiter"):
    company = await create_company(db_session, f"Pipeline Co {role}")
    user = await create_verified_user(
        db_session, company.id, email=f"{role}@pipeline.com", role=role
    )
    await db_session.commit()

    token = create_access_token(
        subject=str(user.id),
        extra_claims={"company_id": str(company.id), "role": user.role},
    )
    client.cookies.set("access_token", token)
    return client


@pytest.fixture(autouse=True)
def disable_email_sending(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mail_service, "send_status_change", lambda *args, **kwargs: None)
    monkeypatch.setattr(mail_service, "send_interview_stage_update", lambda *args, **kwargs: None)
    monkeypatch.setattr(mail_service, "send_html", lambda *args, **kwargs: None)


@pytest.mark.asyncio
async def test_recruiter_can_create_rename_reorder_and_delete_stage(client, db_session) -> None:
    client = await _get_authed_client(client, db_session, "recruiter")

    create_response = await client.post("/api/v1/pipeline", json={"name": "Assessment"})
    assert create_response.status_code == 201
    stage = create_response.json()
    assert stage["name"] == "Assessment"

    rename_response = await client.patch(
        f"/api/v1/pipeline/{stage['id']}", json={"name": "Technical Assessment"}
    )
    assert rename_response.status_code == 200
    assert rename_response.json()["name"] == "Technical Assessment"

    stages_response = await client.get("/api/v1/pipeline")
    assert stages_response.status_code == 200
    stages = stages_response.json()
    reordered_payload = {
        "stages": [
            {"id": item["id"], "order_index": index} for index, item in enumerate(reversed(stages))
        ]
    }
    reorder_response = await client.post("/api/v1/pipeline/reorder", json=reordered_payload)
    assert reorder_response.status_code == 200

    delete_response = await client.delete(f"/api/v1/pipeline/{stage['id']}")
    assert delete_response.status_code == 204


@pytest.mark.asyncio
async def test_manager_cannot_manage_stages(client, db_session) -> None:
    client = await _get_authed_client(client, db_session, "manager")

    response = await client.post("/api/v1/pipeline", json={"name": "Assessment"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_cannot_move_candidate_to_interview_without_meeting_link(client, db_session) -> None:
    company = await create_company(db_session, "Interview Guard Co")
    user = await create_verified_user(
        db_session, company.id, email="guard@pipeline.com", role="recruiter"
    )
    job = await create_job(db_session, company.id, "DevOps Engineer", "open")
    stages = await create_pipeline_stages(db_session)
    application = await create_application(db_session, job.id, stage_id=stages[0].id)
    interview_stage = next(stage for stage in stages if stage.name == "Interview")
    await db_session.commit()
    token = create_access_token(
        subject=str(user.id),
        extra_claims={"company_id": str(company.id), "role": user.role},
    )
    client.cookies.set("access_token", token)

    response = await client.patch(
        f"/api/v1/pipeline/applications/{application.id}/stage",
        json={"stage_id": str(interview_stage.id), "notify_candidate": True},
    )

    # 422 Unprocessable Entity — business-rule precondition (interview stage
    # needs a scheduled interview with a meeting link) → UnprocessableError.
    assert response.status_code == 422
    assert (
        response.json()["detail"]
        == "Interview stage requires a scheduled interview with a meeting link."
    )


@pytest.mark.asyncio
async def test_can_move_candidate_to_interview_when_meeting_link_exists(client, db_session) -> None:
    company = await create_company(db_session, "Interview Ready Co")
    user = await create_verified_user(
        db_session, company.id, email="owner@ready.com", role="recruiter"
    )
    job = await create_job(db_session, company.id, "DevOps Engineer", "open")
    stages = await create_pipeline_stages(db_session)
    application = await create_application(db_session, job.id, stage_id=stages[0].id)
    interview_stage = next(stage for stage in stages if stage.name == "Interview")
    db_session.add(
        Interview(
            application_id=application.id,
            recruiter_id=user.id,
            scheduled_at=datetime.now(UTC),
            duration_minutes=60,
            meeting_url="https://meet.example.com/interview",
            notes="Bring your portfolio",
            status="scheduled",
        )
    )
    await db_session.commit()
    token = create_access_token(
        subject=str(user.id),
        extra_claims={"company_id": str(company.id), "role": user.role},
    )
    client.cookies.set("access_token", token)

    response = await client.patch(
        f"/api/v1/pipeline/applications/{application.id}/stage",
        json={"stage_id": str(interview_stage.id), "notify_candidate": True},
    )

    assert response.status_code == 200
