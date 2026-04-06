from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.core.security import create_access_token
from tests.helpers import create_application, create_company, create_job, create_pipeline_stages, create_verified_user


async def _login(client, user, company_id: str) -> None:
    token = create_access_token(str(user.id), {"company_id": str(company_id), "role": user.role})
    client.cookies.set("access_token", token)


@pytest.mark.asyncio
async def test_recruiter_can_assign_manager_review_and_manager_can_submit(client, db_session) -> None:
    company = await create_company(db_session, "Reviews Co")
    recruiter = await create_verified_user(db_session, company.id, "recruiter@reviews.com", "recruiter")
    manager = await create_verified_user(db_session, company.id, "manager@reviews.com", "manager")
    stages = await create_pipeline_stages(db_session)
    job = await create_job(db_session, company.id, "Platform Engineer", "open")
    application = await create_application(db_session, job.id, stage_id=stages[0].id)
    await db_session.commit()

    await _login(client, recruiter, company.id)

    templates_response = await client.get("/api/v1/reviews/templates")
    assert templates_response.status_code == 200
    templates = templates_response.json()
    assert len(templates) == 1
    template = templates[0]
    assert len(template["criteria"]) > 0

    assign_response = await client.post(
        f"/api/v1/reviews/applications/{application.id}/assignments",
        json={
            "reviewer_id": str(manager.id),
            "template_id": template["id"],
            "due_at": datetime.now(UTC).isoformat(),
        },
    )
    assert assign_response.status_code == 201
    assignment = assign_response.json()
    assert assignment["status"] == "pending"

    list_response = await client.get(f"/api/v1/reviews/applications/{application.id}/assignments")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    await _login(client, manager, company.id)
    submit_response = await client.post(
        f"/api/v1/reviews/assignments/{assignment['id']}/submit",
        json={
            "responses": [
                {
                    "criterion_id": criterion["id"],
                    "score": min(criterion["max_score"], 4),
                    "comment": f"Feedback for {criterion['label']}",
                }
                for criterion in template["criteria"]
            ],
            "overall_comment": "Strong profile and good collaboration signs.",
            "recommendation": "yes",
        },
    )
    assert submit_response.status_code == 200
    submitted = submit_response.json()
    assert submitted["status"] == "submitted"
    assert len(submitted["responses"]) == len(template["criteria"])

    summary_response = await client.get(f"/api/v1/reviews/applications/{application.id}/summary")
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["total_assignments"] == 1
    assert summary["submitted_count"] == 1


@pytest.mark.asyncio
async def test_only_assigned_manager_can_submit_scorecard(client, db_session) -> None:
    company = await create_company(db_session, "Reviews Guard Co")
    recruiter = await create_verified_user(db_session, company.id, "recruiter@guard.com", "recruiter")
    assigned_manager = await create_verified_user(db_session, company.id, "assigned@guard.com", "manager")
    other_manager = await create_verified_user(db_session, company.id, "other@guard.com", "manager")
    stages = await create_pipeline_stages(db_session)
    job = await create_job(db_session, company.id, "QA Engineer", "open")
    application = await create_application(db_session, job.id, stage_id=stages[0].id)
    await db_session.commit()

    await _login(client, recruiter, company.id)
    template = (await client.get("/api/v1/reviews/templates")).json()[0]
    assignment = (
        await client.post(
            f"/api/v1/reviews/applications/{application.id}/assignments",
            json={"reviewer_id": str(assigned_manager.id), "template_id": template["id"]},
        )
    ).json()

    await _login(client, other_manager, company.id)
    submit_response = await client.post(
        f"/api/v1/reviews/assignments/{assignment['id']}/submit",
        json={
            "responses": [{"criterion_id": criterion["id"], "score": 3} for criterion in template["criteria"]],
            "recommendation": "no",
        },
    )
    assert submit_response.status_code == 403
