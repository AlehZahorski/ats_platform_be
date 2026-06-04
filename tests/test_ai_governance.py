"""Faza 4 (plan-naprawy) — AI governance + structured logging.

- structured JSON logs with request-id correlation + PII redaction,
- every LLM call is metered into api_usage_logs with the EU AI Act trail,
- human-in-the-loop: the automation engine never changes a candidate's stage
  (no fully-automated rejection — see also /ai-info FAQ + ADR-0005).
"""

from __future__ import annotations

import json
import logging

import pytest
from fastapi import BackgroundTasks
from sqlalchemy import select

from app.core.enums.automation import AutomationTriggerType
from app.core.logging_utils import JsonFormatter, PiiRedactionFilter, configure_log_format
from app.modules.applications.models import ApiUsageLog
from app.modules.applications.repository import ApplicationRepository
from app.modules.automation.models import AutomationRule
from app.modules.automation.repository import AutomationRepository
from app.modules.automation.schemas import AutomationTriggerPayload
from app.modules.automation.service import AutomationService
from app.modules.email_templates.models import EmailTemplate
from tests.helpers import (
    create_application,
    create_company,
    create_job,
    create_pipeline_stages,
)

# ── structured logging ───────────────────────────────────────────────────────


def test_json_formatter_emits_structured_record() -> None:
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, "hello %s", ("world",), None)
    record.request_id = "abc123"
    record.correlation_id = "corr-1"  # an extra structured field

    data = json.loads(JsonFormatter().format(record))

    assert data["message"] == "hello world"
    assert data["level"] == "INFO"
    assert data["logger"] == "app.test"
    assert data["request_id"] == "abc123"
    assert data["correlation_id"] == "corr-1"


def test_json_formatter_output_is_pii_redacted() -> None:
    record = logging.LogRecord(
        "app.test", logging.INFO, __file__, 1, "contact jane@example.com now", None, None
    )
    PiiRedactionFilter().filter(record)  # redaction runs before the formatter

    out = JsonFormatter().format(record)

    assert "jane@example.com" not in out
    assert "<email-redacted>" in out


def test_configure_log_format_json_applies_json_formatter() -> None:
    root = logging.getLogger()
    snapshot = [(h, h.formatter) for h in root.handlers]
    try:
        configure_log_format("json")
        assert root.handlers
        assert all(isinstance(h.formatter, JsonFormatter) for h in root.handlers)
    finally:
        for handler, fmt in snapshot:
            handler.setFormatter(fmt)


# ── LLM metering (EU AI Act art. 12 / RODO art. 30) ──────────────────────────


@pytest.mark.asyncio
async def test_llm_usage_is_metered_with_ai_act_trail(db_session) -> None:
    comp = await create_company(db_session, "Usage Co")
    job = await create_job(db_session, comp.id, "Role", "open")
    app = await create_application(db_session, job.id, email="u@example.com")
    await db_session.flush()

    meta = {
        "model": "claude-sonnet-4-6",
        "token_usage": {"input_tokens": 100, "output_tokens": 50},
        "cost_usd": 0.0123,
        "prompt_name": "job_analysis",
        "prompt_version": "abc123def456",
        "correlation_id": "corr-xyz",
        "anthropic_request_id": "req_456",
    }
    await ApplicationRepository(db_session).save_api_usage_log(
        comp.id, "job_analyze", meta, application_id=app.id
    )

    row = (
        await db_session.execute(select(ApiUsageLog).where(ApiUsageLog.company_id == comp.id))
    ).scalar_one()
    assert row.application_id == app.id  # ties the call to the data subject
    assert row.anthropic_request_id == "req_456"  # correlate with Anthropic
    assert row.correlation_id == "corr-xyz"
    assert row.prompt_name == "job_analysis"
    assert row.input_tokens == 100
    assert row.output_tokens == 50
    assert row.operation == "job_analyze"


# ── human-in-the-loop ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_automation_rule_never_changes_application_stage(db_session) -> None:
    """The automation engine may only send emails — it must never move a
    candidate's stage, so no fully-automated rejection is possible."""
    comp = await create_company(db_session, "HITL Co")
    stages = await create_pipeline_stages(db_session)
    job = await create_job(db_session, comp.id, "Role", "open")
    app = await create_application(db_session, job.id, stage_id=stages[0].id)
    tpl = EmailTemplate(
        company_id=comp.id, name="Ack", type="custom", subject="s", body="b", language="en"
    )
    db_session.add(tpl)
    await db_session.flush()
    db_session.add(
        AutomationRule(
            company_id=comp.id,
            name="r",
            trigger_type="application_created",
            trigger_value=None,
            template_id=tpl.id,
            is_active=True,
        )
    )
    await db_session.flush()

    fired = await AutomationService(AutomationRepository(db_session)).trigger(
        AutomationTriggerPayload(
            trigger_type=AutomationTriggerType.application_created,
            trigger_value=None,
            application_id=app.id,
            company_id=comp.id,
            variables={"candidate_name": "X"},
        ),
        BackgroundTasks(),
        "x@example.com",
    )

    assert fired is True  # the rule did fire (sent an email)
    await db_session.refresh(app)
    assert app.stage_id == stages[0].id  # ...but the candidate was NOT moved
