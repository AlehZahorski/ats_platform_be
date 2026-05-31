from __future__ import annotations

import re
import uuid
from typing import Any

from app.core.base_service import BaseService
from app.core.exceptions import NotFoundError
from app.modules.email_templates.models import EmailTemplate
from app.modules.email_templates.repository import EmailTemplateRepository
from app.modules.email_templates.schemas import (
    EmailTemplateCreate,
    EmailTemplatePreview,
    EmailTemplateUpdate,
)

DEFAULT_VARIABLES: dict[str, str] = {
    "candidate_name": "John Doe",
    "candidate_email": "candidate@example.com",
    "job_title": "Senior Developer",
    "company_name": "Acme Corp",
    "stage_name": "Interview",
    "tracking_url": "https://app.example.com/track/TOKEN",
    "interview_date": "2024-12-01 14:00",
    "interview_url": "https://meet.example.com/abc123",
}


class EmailTemplateService(BaseService[EmailTemplateRepository]):
    async def create(self, company_id: uuid.UUID, data: EmailTemplateCreate) -> EmailTemplate:
        return await self.repository.create(company_id, data)

    async def list(
        self,
        company_id: uuid.UUID,
        language: str | None = None,
        type: str | None = None,
    ) -> list[EmailTemplate]:
        return await self.repository.list_by_company(company_id, language=language, type=type)

    async def get(self, template_id: uuid.UUID, company_id: uuid.UUID) -> EmailTemplate:
        template = await self.repository.get_by_id_and_company(template_id, company_id)
        if not template:
            raise NotFoundError("Template not found.")
        return template

    async def update(
        self, template_id: uuid.UUID, company_id: uuid.UUID, data: EmailTemplateUpdate
    ) -> EmailTemplate:
        template = await self.get(template_id, company_id)
        return await self.repository.update(template, data)

    async def delete(self, template_id: uuid.UUID, company_id: uuid.UUID) -> None:
        template = await self.get(template_id, company_id)
        await self.repository.delete(template)

    async def preview(
        self,
        template_id: uuid.UUID,
        company_id: uuid.UUID,
        variables: dict[str, Any] | None = None,
    ) -> EmailTemplatePreview:
        template = await self.get(template_id, company_id)
        merged = {**DEFAULT_VARIABLES, **(variables or {})}
        subject, body = self._render(template.subject, template.body, merged)
        return EmailTemplatePreview(subject=subject, body=body)

    async def render_for_send(
        self,
        template: EmailTemplate,
        variables: dict[str, Any],
    ) -> tuple[str, str]:
        merged = {**DEFAULT_VARIABLES, **variables}
        return self._render(template.subject, template.body, merged)

    @staticmethod
    def _render(subject: str, body: str, variables: dict[str, Any]) -> tuple[str, str]:
        def replace(text: str) -> str:
            def replacer(match: re.Match) -> str:
                key = match.group(1).strip()
                return str(variables.get(key, f"{{{{{key}}}}}"))

            return re.sub(r"\{\{(\w+)\}\}", replacer, text)

        return replace(subject), replace(body)
