"""Tests for the jobs module."""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.helpers import create_company, create_verified_user


async def _login(client: AsyncClient, email: str, password: str = "testpassword") -> None:
    """Helper: log in and set cookie on the test client."""
    from app.core.security import create_access_token
    # Bypass SMTP by injecting a valid access token cookie directly
    # (test_login_success_sets_cookie already validates the real flow)
    pass


async def _get_authed_client(client: AsyncClient, db_session, suffix: str = "") -> tuple[AsyncClient, object]:
    """Seed a company + user, inject auth cookie, return (client, company)."""
    from app.core.security import create_access_token

    company = await create_company(db_session, f"Jobs Co {suffix}")
    user = await create_verified_user(db_session, company.id, email=f"hr{suffix}@jobs.com")
    await db_session.commit()

    token = create_access_token(
        subject=str(user.id),
        extra_claims={"company_id": str(company.id), "role": user.role},
    )
    client.cookies.set("access_token", token)
    return client, company


@pytest.mark.asyncio
async def test_create_job(client: AsyncClient, db_session) -> None:
    client, _ = await _get_authed_client(client, db_session, "create")

    response = await client.post(
        "/api/v1/jobs",
        json={"title": "Backend Engineer", "status": "draft"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Backend Engineer"
    assert data["status"] == "draft"
    assert "id" in data


@pytest.mark.asyncio
async def test_list_jobs(client: AsyncClient, db_session) -> None:
    client, _ = await _get_authed_client(client, db_session, "list")

    await client.post("/api/v1/jobs", json={"title": "Job A", "status": "open"})
    await client.post("/api/v1/jobs", json={"title": "Job B", "status": "open"})

    response = await client.get("/api/v1/jobs")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 2
    assert len(data["items"]) >= 2


@pytest.mark.asyncio
async def test_get_job_not_found(client: AsyncClient, db_session) -> None:
    client, _ = await _get_authed_client(client, db_session, "notfound")
    import uuid
    response = await client.get(f"/api/v1/jobs/{uuid.uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_job(client: AsyncClient, db_session) -> None:
    client, _ = await _get_authed_client(client, db_session, "update")

    create_resp = await client.post(
        "/api/v1/jobs",
        json={"title": "Old Title", "status": "draft"},
    )
    job_id = create_resp.json()["id"]

    response = await client.patch(
        f"/api/v1/jobs/{job_id}",
        json={"title": "New Title", "status": "open"},
    )
    assert response.status_code == 200
    assert response.json()["title"] == "New Title"
    assert response.json()["status"] == "open"


@pytest.mark.asyncio
async def test_delete_job(client: AsyncClient, db_session) -> None:
    client, _ = await _get_authed_client(client, db_session, "delete")

    create_resp = await client.post(
        "/api/v1/jobs",
        json={"title": "To Delete", "status": "draft"},
    )
    job_id = create_resp.json()["id"]

    response = await client.delete(f"/api/v1/jobs/{job_id}")
    assert response.status_code == 204

    get_resp = await client.get(f"/api/v1/jobs/{job_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_jobs_company_isolation(client: AsyncClient, db_session) -> None:
    """Users from company A must not see jobs from company B."""
    from app.core.security import create_access_token

    company_a = await create_company(db_session, "Company A Isolation")
    user_a = await create_verified_user(db_session, company_a.id, "a@isolation.com")

    company_b = await create_company(db_session, "Company B Isolation")
    user_b = await create_verified_user(db_session, company_b.id, "b@isolation.com")
    await db_session.commit()

    # Create job as company A
    token_a = create_access_token(str(user_a.id), {"company_id": str(company_a.id), "role": "owner"})
    client.cookies.set("access_token", token_a)
    create_resp = await client.post("/api/v1/jobs", json={"title": "Company A Job", "status": "open"})
    job_id = create_resp.json()["id"]

    # Try to access as company B
    token_b = create_access_token(str(user_b.id), {"company_id": str(company_b.id), "role": "owner"})
    client.cookies.set("access_token", token_b)
    response = await client.get(f"/api/v1/jobs/{job_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_filter_jobs_by_status(client: AsyncClient, db_session) -> None:
    client, _ = await _get_authed_client(client, db_session, "filter")

    await client.post("/api/v1/jobs", json={"title": "Open Job", "status": "open"})
    await client.post("/api/v1/jobs", json={"title": "Draft Job", "status": "draft"})

    response = await client.get("/api/v1/jobs?status=open")
    assert response.status_code == 200
    items = response.json()["items"]
    assert all(j["status"] == "open" for j in items)
