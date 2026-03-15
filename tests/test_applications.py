"""Tests for the applications module."""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.helpers import (
    create_company,
    create_job,
    create_pipeline_stages,
    create_verified_user,
)


async def _authed_client(client: AsyncClient, db_session, suffix: str = ""):
    from app.core.security import create_access_token

    company = await create_company(db_session, f"App Co {suffix}")
    user = await create_verified_user(db_session, company.id, f"hr{suffix}@appco.com")
    stages = await create_pipeline_stages(db_session)
    job = await create_job(db_session, company.id, "Test Role", "open")
    await db_session.commit()

    token = create_access_token(str(user.id), {"company_id": str(company.id), "role": "owner"})
    client.cookies.set("access_token", token)
    return client, company, job, stages


@pytest.mark.asyncio
async def test_submit_application(client: AsyncClient, db_session) -> None:
    _, _, job, _ = await _authed_client(client, db_session, "submit")

    # Clear auth cookies — this is a public endpoint
    client.cookies.clear()

    response = await client.post(
        f"/api/v1/applications/apply/{job.id}",
        data={
            "first_name": "Jane",
            "last_name": "Doe",
            "email": "jane@example.com",
            "phone": "555-0100",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["first_name"] == "Jane"
    assert data["email"] == "jane@example.com"
    assert "public_token" in data
    assert len(data["public_token"]) > 10


@pytest.mark.asyncio
async def test_apply_to_closed_job(client: AsyncClient, db_session) -> None:
    _, _, _, _ = await _authed_client(client, db_session, "closed")
    company = await create_company(db_session, "Closed Co")
    closed_job = await create_job(db_session, company.id, "Closed Position", "closed")
    await db_session.commit()

    client.cookies.clear()
    response = await client.post(
        f"/api/v1/applications/apply/{closed_job.id}",
        data={"first_name": "Bob", "last_name": "Smith", "email": "bob@example.com"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_track_application(client: AsyncClient, db_session) -> None:
    _, _, job, _ = await _authed_client(client, db_session, "track")
    client.cookies.clear()

    apply_resp = await client.post(
        f"/api/v1/applications/apply/{job.id}",
        data={"first_name": "Alice", "last_name": "Track", "email": "alice@track.com"},
    )
    token = apply_resp.json()["public_token"]

    track_resp = await client.get(f"/api/v1/applications/track/{token}")
    assert track_resp.status_code == 200
    data = track_resp.json()
    assert data["first_name"] == "Alice"


@pytest.mark.asyncio
async def test_track_invalid_token(client: AsyncClient, db_session) -> None:
    client.cookies.clear()
    response = await client.get("/api/v1/applications/track/invalid-token-xyz")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_applications_requires_auth(client: AsyncClient, db_session) -> None:
    client.cookies.clear()
    response = await client.get("/api/v1/applications")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_applications(client: AsyncClient, db_session) -> None:
    authed, _, job, _ = await _authed_client(client, db_session, "listreq")

    # Submit two applications (unauthenticated)
    client.cookies.clear()
    for i in range(2):
        await client.post(
            f"/api/v1/applications/apply/{job.id}",
            data={
                "first_name": f"Candidate{i}",
                "last_name": "Test",
                "email": f"c{i}@example.com",
            },
        )

    # Re-authenticate
    from app.core.security import create_access_token
    from tests.helpers import create_company, create_verified_user
    company = await create_company(db_session, "ListCheck Co")
    user = await create_verified_user(db_session, company.id, "list@check.com")
    await db_session.commit()
    token = create_access_token(str(user.id), {"company_id": str(company.id), "role": "owner"})
    client.cookies.set("access_token", token)

    response = await client.get("/api/v1/applications")
    assert response.status_code == 200
    assert "items" in response.json()
    assert "total" in response.json()


@pytest.mark.asyncio
async def test_score_application(client: AsyncClient, db_session) -> None:
    authed, _, job, _ = await _authed_client(client, db_session, "score")

    client.cookies.clear()
    apply_resp = await client.post(
        f"/api/v1/applications/apply/{job.id}",
        data={"first_name": "Score", "last_name": "Me", "email": "score@test.com"},
    )
    app_id = apply_resp.json()["id"]

    # Re-auth to score
    from app.core.security import create_access_token
    company = await create_company(db_session, "Score Co")
    user = await create_verified_user(db_session, company.id, "scorer@test.com")
    await db_session.commit()
    token = create_access_token(str(user.id), {"company_id": str(company.id), "role": "owner"})
    client.cookies.set("access_token", token)

    response = await client.post(
        f"/api/v1/applications/{app_id}/score",
        json={"communication": 4, "technical": 5, "culture_fit": 3},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["communication"] == 4
    assert data["technical"] == 5
    assert data["culture_fit"] == 3


@pytest.mark.asyncio
async def test_public_token_is_unique(client: AsyncClient, db_session) -> None:
    _, _, job, _ = await _authed_client(client, db_session, "unique")
    client.cookies.clear()

    tokens = []
    for i in range(5):
        resp = await client.post(
            f"/api/v1/applications/apply/{job.id}",
            data={
                "first_name": f"Uniq{i}",
                "last_name": "Test",
                "email": f"uniq{i}@test.com",
            },
        )
        tokens.append(resp.json()["public_token"])

    assert len(set(tokens)) == 5, "All public tokens must be unique"
