"""Shared test helpers for creating seeded DB state."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.modules.companies.models import Company
from app.modules.jobs.models import Job
from app.modules.pipeline.models import PipelineStage
from app.modules.users.models import User


async def create_company(db: AsyncSession, name: str = "Test Company") -> Company:
    company = Company(name=name)
    db.add(company)
    await db.flush()
    return company


async def create_verified_user(
    db: AsyncSession,
    company_id: uuid.UUID,
    email: str = "hr@test.com",
    role: str = "owner",
) -> User:
    user = User(
        company_id=company_id,
        email=email,
        password_hash=hash_password("testpassword"),
        role=role,
        is_verified=True,
    )
    db.add(user)
    await db.flush()
    return user


async def create_job(
    db: AsyncSession,
    company_id: uuid.UUID,
    title: str = "Software Engineer",
    status: str = "open",
) -> Job:
    job = Job(company_id=company_id, title=title, status=status)
    db.add(job)
    await db.flush()
    return job


async def create_pipeline_stages(db: AsyncSession) -> list[PipelineStage]:
    stages = [
        PipelineStage(name="Applied", order_index=1),
        PipelineStage(name="Screening", order_index=2),
        PipelineStage(name="Interview", order_index=3),
        PipelineStage(name="Offer", order_index=4),
        PipelineStage(name="Hired", order_index=5),
        PipelineStage(name="Rejected", order_index=6),
    ]
    for s in stages:
        db.add(s)
    await db.flush()
    return stages
