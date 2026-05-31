"""Admin AI-usage analytics (F-23).

Exercises AdminUsageService aggregation directly against seeded ApiUsageLog
rows — no admin-auth plumbing needed for the aggregation logic itself.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete

from app.modules.admins.usage_service import AdminUsageService
from app.modules.applications.models import ApiUsageLog
from tests.helpers import create_company


async def _reset_usage(db) -> None:
    """The shared test session is not rolled back between tests, so wipe the
    usage table first to keep cross-tenant totals deterministic."""
    await db.execute(delete(ApiUsageLog))
    await db.flush()


async def _add_log(db, *, company_id, operation, llm_model, inp, out, cost, when=None):
    log = ApiUsageLog(
        company_id=company_id,
        operation=operation,
        llm_model=llm_model,
        prompt_name=operation,
        input_tokens=inp,
        output_tokens=out,
        cost_usd=cost,
    )
    if when is not None:
        log.created_at = when
    db.add(log)
    await db.flush()
    return log


@pytest.mark.asyncio
async def test_usage_report_aggregates_by_company(db_session):
    await _reset_usage(db_session)
    acme = await create_company(db_session, name="Acme")
    globex = await create_company(db_session, name="Globex")

    await _add_log(
        db_session,
        company_id=acme.id,
        operation="cv_parsing",
        llm_model="claude-haiku-4-5",
        inp=100,
        out=50,
        cost=0.001,
    )
    await _add_log(
        db_session,
        company_id=acme.id,
        operation="job_match",
        llm_model="claude-sonnet-4-6",
        inp=200,
        out=80,
        cost=0.005,
    )
    await _add_log(
        db_session,
        company_id=globex.id,
        operation="cv_parsing",
        llm_model="claude-haiku-4-5",
        inp=300,
        out=120,
        cost=0.002,
    )
    await db_session.commit()

    report = await AdminUsageService(db_session).usage_report(days=None)

    # Overview totals
    assert report.overview.total_calls == 3
    assert report.overview.total_input_tokens == 600
    assert report.overview.total_output_tokens == 250
    assert report.overview.total_tokens == 850
    assert report.overview.companies_using == 2
    assert round(report.overview.total_cost_usd, 6) == 0.008

    # By company — Acme spent more, so it sorts first (order_by cost desc)
    assert report.by_company[0].company_name == "Acme"
    assert report.by_company[0].calls == 2
    assert report.by_company[0].total_tokens == 430
    assert round(report.by_company[0].cost_usd, 6) == 0.006

    # By operation + by model present
    ops = {r.operation for r in report.by_operation}
    assert ops == {"cv_parsing", "job_match"}
    models = {r.llm_model for r in report.by_model}
    assert "claude-haiku-4-5" in models and "claude-sonnet-4-6" in models

    # Recent calls present, capped, carry derived total_tokens
    assert len(report.recent) == 3
    assert all(r.total_tokens == r.input_tokens + r.output_tokens for r in report.recent)


@pytest.mark.asyncio
async def test_usage_report_respects_days_window(db_session):
    await _reset_usage(db_session)
    acme = await create_company(db_session, name="Acme Old")
    now = datetime.now(UTC)

    await _add_log(
        db_session,
        company_id=acme.id,
        operation="cv_parsing",
        llm_model="m",
        inp=10,
        out=10,
        cost=0.001,
        when=now,
    )
    await _add_log(
        db_session,
        company_id=acme.id,
        operation="cv_parsing",
        llm_model="m",
        inp=10,
        out=10,
        cost=0.001,
        when=now - timedelta(days=40),
    )
    await db_session.commit()

    # 30-day window excludes the 40-day-old row.
    report = await AdminUsageService(db_session).usage_report(days=30)
    assert report.overview.total_calls == 1
    assert report.overview.period_days == 30

    # All-time includes both.
    report_all = await AdminUsageService(db_session).usage_report(days=None)
    assert report_all.overview.total_calls == 2
    assert report_all.overview.period_days is None


@pytest.mark.asyncio
async def test_usage_report_empty(db_session):
    await _reset_usage(db_session)
    report = await AdminUsageService(db_session).usage_report(days=None)
    assert report.overview.total_calls == 0
    assert report.overview.total_cost_usd == 0
    assert report.by_company == []
    assert report.recent == []
