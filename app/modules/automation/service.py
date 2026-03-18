from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.application_events.models import ApplicationEvent
from app.modules.audit.models import AuditLog
from app.modules.automation.models import AutomationRule
from app.modules.automation.repository import AutomationRepository
from app.modules.automation.schemas import (
    AutomationRuleCreate,
    AutomationRuleUpdate,
    AutomationTriggerPayload,
)
from app.modules.email_templates.service import EmailTemplateService
from app.services.mailer import mail_service


class AutomationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = AutomationRepository(db)

    # ── CRUD ──────────────────────────────────────────────────────────────
    async def create(self, company_id: uuid.UUID, data: AutomationRuleCreate) -> AutomationRule:
        return await self.repo.create(company_id, data)

    async def list(self, company_id: uuid.UUID) -> list[AutomationRule]:
        return await self.repo.list(company_id)

    async def get(self, rule_id: uuid.UUID, company_id: uuid.UUID) -> AutomationRule:
        rule = await self.repo.get_by_id(rule_id, company_id)
        if not rule:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Automation rule not found")
        return rule

    async def update(
        self, rule_id: uuid.UUID, company_id: uuid.UUID, data: AutomationRuleUpdate
    ) -> AutomationRule:
        rule = await self.get(rule_id, company_id)
        return await self.repo.update(rule, data)

    async def delete(self, rule_id: uuid.UUID, company_id: uuid.UUID) -> None:
        rule = await self.get(rule_id, company_id)
        await self.repo.delete(rule)

    async def toggle(self, rule_id: uuid.UUID, company_id: uuid.UUID) -> AutomationRule:
        rule = await self.get(rule_id, company_id)
        return await self.repo.update(rule, AutomationRuleUpdate(is_active=not rule.is_active))

    # ── Event-driven execution ─────────────────────────────────────────────
    async def trigger(
        self,
        payload: AutomationTriggerPayload,
        background_tasks: BackgroundTasks,
        candidate_email: str,
    ) -> None:
        """
        Called when a system event occurs.
        Finds matching active rules and schedules email sending in background.
        """
        rules = await self.repo.get_matching_rules(
            company_id=payload.company_id,
            trigger_type=payload.trigger_type,
            trigger_value=payload.trigger_value,
        )

        for rule in rules:
            if rule.template:
                background_tasks.add_task(
                    self._execute_rule,
                    rule=rule,
                    application_id=payload.application_id,
                    company_id=payload.company_id,
                    candidate_email=candidate_email,
                    variables=payload.variables,
                )

    async def _execute_rule(
        self,
        rule: AutomationRule,
        application_id: uuid.UUID,
        company_id: uuid.UUID,
        candidate_email: str,
        variables: dict[str, Any],
    ) -> None:
        """Background task: render template and send email."""
        from app.core.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            try:
                template_svc = EmailTemplateService(db)
                subject, body = await template_svc.render_for_send(rule.template, variables)

                # Send email synchronously inside background task
                from app.services.mailer import _send_smtp
                _send_smtp(candidate_email, subject, body)

                # Log application event
                event = ApplicationEvent(
                    application_id=application_id,
                    company_id=company_id,
                    event_type="email_sent",
                    event_value=rule.template.name,
                    metadata_={"rule_id": str(rule.id), "template_id": str(rule.template_id)},
                )
                db.add(event)

                # Audit log
                audit = AuditLog(
                    company_id=company_id,
                    action="automation_triggered",
                    entity_type="application",
                    entity_id=application_id,
                    metadata_={"rule_name": rule.name},
                )
                db.add(audit)

                await db.commit()
            except Exception as e:
                await db.rollback()
                # Log but don't crash — automation failures are non-critical
                print(f"[Automation] Rule {rule.id} failed: {e}")