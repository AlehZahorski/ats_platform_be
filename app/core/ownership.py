"""Tenant-isolation guards (Faza 1, plan-naprawy).

Applications and everything hanging off them (notes, scores, interviews, tags,
stage history, consents, cv-parse jobs, matches) are scoped to a company
through the application's job: ``Application -> Job.company_id``. Any endpoint
that accepts an ``{application_id}`` (or an interview/field id derived from one)
must verify the resource belongs to the caller's company, otherwise company A
can read or mutate company B's candidate by guessing a UUID (IDOR).

This module centralises that check so every call site uses the exact same,
audited query and returns a uniform 404 (never revealing that the id exists in
another tenant).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.i18n import t
from app.modules.applications.models import Application
from app.modules.jobs.models import Job


async def ensure_application_in_company(
    db: AsyncSession, application_id: uuid.UUID, company_id: uuid.UUID
) -> Application:
    """Return the application iff it belongs to ``company_id``, else raise 404.

    The 404 (not 403) is deliberate: a cross-tenant id must be indistinguishable
    from a non-existent one so an attacker can't enumerate which ids exist in
    other companies.
    """
    result = await db.execute(
        select(Application)
        .join(Job, Application.job_id == Job.id)
        .where(Application.id == application_id, Job.company_id == company_id)
    )
    application = result.scalar_one_or_none()
    if application is None:
        raise NotFoundError(t("applications.not_found"))
    return application
