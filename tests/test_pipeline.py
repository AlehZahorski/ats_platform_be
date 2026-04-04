from __future__ import annotations

import pytest

from app.core.security import create_access_token
from tests.helpers import create_company, create_verified_user


async def _get_authed_client(client, db_session, role: str = "recruiter"):
    company = await create_company(db_session, f"Pipeline Co {role}")
    user = await create_verified_user(db_session, company.id, email=f"{role}@pipeline.com", role=role)
    await db_session.commit()

    token = create_access_token(
        subject=str(user.id),
        extra_claims={"company_id": str(company.id), "role": user.role},
    )
    client.cookies.set("access_token", token)
    return client


@pytest.mark.asyncio
async def test_recruiter_can_create_rename_reorder_and_delete_stage(client, db_session) -> None:
    client = await _get_authed_client(client, db_session, "recruiter")

    create_response = await client.post("/api/v1/pipeline", json={"name": "Assessment"})
    assert create_response.status_code == 201
    stage = create_response.json()
    assert stage["name"] == "Assessment"

    rename_response = await client.patch(f"/api/v1/pipeline/{stage['id']}", json={"name": "Technical Assessment"})
    assert rename_response.status_code == 200
    assert rename_response.json()["name"] == "Technical Assessment"

    stages_response = await client.get("/api/v1/pipeline")
    assert stages_response.status_code == 200
    stages = stages_response.json()
    reordered_payload = {
        "stages": [
            {"id": item["id"], "order_index": index}
            for index, item in enumerate(reversed(stages))
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
