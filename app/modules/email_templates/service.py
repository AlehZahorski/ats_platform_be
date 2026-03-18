from __future__ import annotations

import re
import uuid
from typing import Any, Optional

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.email_templates.models import EmailTemplate
from app.modules.email_templates.repository import EmailTemplateRepository
from app.modules.email_templates.schemas import (
    EmailTemplateCreate,
    EmailTemplatePreview,
    EmailTemplateUpdate,
)

# Default variables available in all templates
DEFAULT_VARIABLES = {
    "candidate_name": "John Doe",
    "candidate_email": "candidate@example.com",
    "job_title": "Senior Developer",
    "company_name": "Acme Corp",
    "stage_name": "Interview",
    "tracking_url": "https://app.example.com/track/TOKEN",
    "interview_date": "2024-12-01 14:00",
    "interview_url": "https://meet.example.com/abc123",
}


def render_template(subject: str, body: str, variables: dict[str, Any]) -> tuple[str, str]:
    """Replace {{variable}} placeholders with actual values."""
    def replace(text: str) -> str:
        def replacer(match: re.Match) -> str:
            key = match.group(1).strip()
            return str(variables.get(key, f"{{{{{key}}}}}"))
        return re.sub(r"\{\{(\w+)\}\}", replacer, text)

    return replace(subject), replace(body)


class EmailTemplateService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = EmailTemplateRepository(db)

    async def create(self, company_id: uuid.UUID, data: EmailTemplateCreate) -> EmailTemplate:
        return await self.repo.create(company_id, data)

    async def list(
        self,
        company_id: uuid.UUID,
        language: Optional[str] = None,
        type: Optional[str] = None,
    ) -> list[EmailTemplate]:
        return await self.repo.list(company_id, language=language, type=type)

    async def get(self, template_id: uuid.UUID, company_id: uuid.UUID) -> EmailTemplate:
        template = await self.repo.get_by_id(template_id, company_id)
        if not template:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
        return template

    async def update(
        self, template_id: uuid.UUID, company_id: uuid.UUID, data: EmailTemplateUpdate
    ) -> EmailTemplate:
        template = await self.get(template_id, company_id)
        return await self.repo.update(template, data)

    async def delete(self, template_id: uuid.UUID, company_id: uuid.UUID) -> None:
        template = await self.get(template_id, company_id)
        await self.repo.delete(template)

    async def preview(
        self,
        template_id: uuid.UUID,
        company_id: uuid.UUID,
        variables: Optional[dict[str, Any]] = None,
    ) -> EmailTemplatePreview:
        template = await self.get(template_id, company_id)
        merged = {**DEFAULT_VARIABLES, **(variables or {})}
        subject, body = render_template(template.subject, template.body, merged)
        return EmailTemplatePreview(subject=subject, body=body)

    async def render_for_send(
        self,
        template: EmailTemplate,
        variables: dict[str, Any],
    ) -> tuple[str, str]:
        """Render a template for actual sending. Returns (subject, body)."""
        merged = {**DEFAULT_VARIABLES, **variables}
        return render_template(template.subject, template.body, merged)