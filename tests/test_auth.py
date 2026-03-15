"""Tests for the authentication module."""
from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_signup_company_success(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/signup-company",
        json={
            "company_name": "Acme Corp",
            "email": "owner@acme.com",
            "password": "strongpassword123",
        },
    )
    assert response.status_code == 201
    assert "message" in response.json()


@pytest.mark.asyncio
async def test_signup_duplicate_email(client: AsyncClient) -> None:
    payload = {
        "company_name": "Acme Corp 2",
        "email": "duplicate@acme.com",
        "password": "strongpassword123",
    }
    await client.post("/api/v1/auth/signup-company", json=payload)
    response = await client.post("/api/v1/auth/signup-company", json=payload)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_login_unverified_user(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/signup-company",
        json={
            "company_name": "Beta Inc",
            "email": "beta@beta.com",
            "password": "password123",
        },
    )
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "beta@beta.com", "password": "password123"},
    )
    # Unverified users cannot log in
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, db_session) -> None:
    # Create and verify a user directly
    from app.core.security import hash_password
    from app.modules.companies.models import Company
    from app.modules.users.models import User

    company = Company(name="Test Co")
    db_session.add(company)
    await db_session.flush()

    user = User(
        company_id=company.id,
        email="verified@test.com",
        password_hash=hash_password("correctpassword"),
        role="owner",
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "verified@test.com", "password": "wrongpassword"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_success_sets_cookie(client: AsyncClient, db_session) -> None:
    from app.core.security import hash_password
    from app.modules.companies.models import Company
    from app.modules.users.models import User

    company = Company(name="Cookie Co")
    db_session.add(company)
    await db_session.flush()

    user = User(
        company_id=company.id,
        email="cookie@test.com",
        password_hash=hash_password("mypassword"),
        role="owner",
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "cookie@test.com", "password": "mypassword"},
    )
    assert response.status_code == 200
    assert "access_token" in response.cookies


@pytest.mark.asyncio
async def test_me_unauthenticated(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout(client: AsyncClient, db_session) -> None:
    from app.core.security import hash_password
    from app.modules.companies.models import Company
    from app.modules.users.models import User

    company = Company(name="Logout Co")
    db_session.add(company)
    await db_session.flush()

    user = User(
        company_id=company.id,
        email="logout@test.com",
        password_hash=hash_password("password"),
        role="owner",
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()

    await client.post(
        "/api/v1/auth/login",
        json={"email": "logout@test.com", "password": "password"},
    )
    response = await client.post("/api/v1/auth/logout")
    assert response.status_code == 200
    # Cookie should be cleared
    assert response.cookies.get("access_token") is None
