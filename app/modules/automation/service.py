from __future__ import annotations

import uuid
from typing import Any

from fastapi import BackgroundTasks

from app.core.base_service import BaseService
from app.core.exceptions import NotFoundError
from app.core.i18n import t
from app.modules.application_events.models import ApplicationEvent
from app.modules.audit.models import AuditLog
from app.modules.automation.models import AutomationRule
from app.modules.automation.repository import AutomationRepository
from app.modules.automation.schemas import (
    AutomationRuleCreate,
    AutomationRuleUpdate,
    AutomationTriggerPayload,
)


class AutomationService(BaseService[AutomationRepository]):

    async def create(self, company_id: uuid.UUID, data: AutomationRuleCreate) -> AutomationRule:
        return await self.repository.create(company_id, data)

    async def list(self, company_id: uuid.UUID) -> list[AutomationRule]:
        return await self.repository.list_by_company(company_id)

    async def get(self, rule_id: uuid.UUID, company_id: uuid.UUID) -> AutomationRule:
        rule = await self.repository.get_by_id_and_company(rule_id, company_id)
        if not rule:
            raise NotFoundError(t("automation.rule_not_found"))
        return rule

    async def update(
        self, rule_id: uuid.UUID, company_id: uuid.UUID, data: AutomationRuleUpdate
    ) -> AutomationRule:
        rule = await self.get(rule_id, company_id)
        return await self.repository.update(rule, data)

    async def delete(self, rule_id: uuid.UUID, company_id: uuid.UUID) -> None:
        rule = await self.get(rule_id, company_id)
        await self.repository.delete(rule)

    async def toggle(self, rule_id: uuid.UUID, company_id: uuid.UUID) -> AutomationRule:
        rule = await self.get(rule_id, company_id)
        return await self.repository.update(rule, AutomationRuleUpdate(is_active=not rule.is_active))

    async def trigger(
        self,
        payload: AutomationTriggerPayload,
        background_tasks: BackgroundTasks,
        candidate_email: str,
    ) -> None:
        rules = await self.repository.get_matching_rules(
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

    @staticmethod
    async def _execute_rule(
        rule: AutomationRule,
        application_id: uuid.UUID,
        company_id: uuid.UUID,
        candidate_email: str,
        variables: dict[str, Any],
    ) -> None:
        from app.core.database import AsyncSessionLocal
        from app.modules.email_templates.service import EmailTemplateService
        from app.services.mailer import _send_smtp

        async with AsyncSessionLocal() as db:
            try:
                from app.modules.email_templates.repository import EmailTemplateRepository
                template_svc = EmailTemplateService(EmailTemplateRepository(db))
                subject, body = await template_svc.render_for_send(rule.template, variables)

                _send_smtp(candidate_email, subject, body)

                db.add(ApplicationEvent(
                    application_id=application_id,
                    company_id=company_id,
                    event_type="email_sent",
                    event_value=rule.template.name,
                    metadata_={"rule_id": str(rule.id), "template_id": str(rule.template_id)},
                ))
                db.add(AuditLog(
                    company_id=company_id,
                    action="automation_triggered",
                    entity_type="application",
                    entity_id=application_id,
                    metadata_={"rule_name": rule.name},
                ))
                await db.commit()
            except Exception as e:
                await db.rollback()
                print(f"[Automation] Rule {rule.id} failed: {e}")
