from __future__ import annotations

import logging
import uuid

logger = logging.getLogger(__name__)

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
from app.modules.email_templates.repository import EmailTemplateRepository
from app.modules.email_templates.service import EmailTemplateService
from app.services.mailer import _send_smtp


class AutomationService(BaseService[AutomationRepository]):
    async def _ensure_template_in_company(
        self, template_id: uuid.UUID | None, company_id: uuid.UUID
    ) -> None:
        # Tenant isolation: a rule may only reference an email template owned by
        # the same company. None means "no template" — nothing to check.
        if template_id is None:
            return
        template = await EmailTemplateRepository(self.repository.db).get_by_id_and_company(
            template_id, company_id
        )
        if template is None:
            raise NotFoundError(t("forms.template_not_found"))

    async def create(self, company_id: uuid.UUID, data: AutomationRuleCreate) -> AutomationRule:
        await self._ensure_template_in_company(data.template_id, company_id)
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
        await self._ensure_template_in_company(data.template_id, company_id)
        return await self.repository.update(rule, data)

    async def delete(self, rule_id: uuid.UUID, company_id: uuid.UUID) -> None:
        rule = await self.get(rule_id, company_id)
        await self.repository.delete(rule)

    async def toggle(self, rule_id: uuid.UUID, company_id: uuid.UUID) -> AutomationRule:
        rule = await self.get(rule_id, company_id)
        return await self.repository.update(
            rule, AutomationRuleUpdate(is_active=not rule.is_active)
        )

    async def trigger(
        self,
        payload: AutomationTriggerPayload,
        background_tasks: BackgroundTasks,
        candidate_email: str,
    ) -> bool:
        """Fire matching automation rules. Returns True if at least one rule
        with a template was scheduled (so the caller can skip a default
        notification and avoid double-sending)."""
        rules = await self.repository.get_matching_rules(
            company_id=payload.company_id,
            trigger_type=payload.trigger_type,
            trigger_value=payload.trigger_value,
        )
        if not rules:
            return False

        template_svc = EmailTemplateService(EmailTemplateRepository(self.repository.db))
        fired = False
        for rule in rules:
            if not rule.template:
                continue
            # Render now; defer ONLY the email I/O to the background. The
            # email_sent event + automation audit are recorded transactionally
            # with the request (so they're testable and roll back together with
            # the request) instead of in a detached background session.
            subject, body = await template_svc.render_for_send(rule.template, payload.variables)
            background_tasks.add_task(_send_smtp, candidate_email, subject, body)
            self.repository.db.add(
                ApplicationEvent(
                    application_id=payload.application_id,
                    company_id=payload.company_id,
                    event_type="email_sent",
                    event_value=rule.template.name,
                    metadata_={"rule_id": str(rule.id), "template_id": str(rule.template_id)},
                )
            )
            self.repository.db.add(
                AuditLog(
                    company_id=payload.company_id,
                    action="automation_triggered",
                    entity_type="application",
                    entity_id=payload.application_id,
                    metadata_={"rule_name": rule.name},
                )
            )
            fired = True
        return fired
