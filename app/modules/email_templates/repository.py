from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.email_templates.models import EmailTemplate
from app.modules.email_templates.schemas import EmailTemplateCreate, EmailTemplateUpdate


class EmailTemplateRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, company_id: uuid.UUID, data: EmailTemplateCreate) -> EmailTemplate:
        template = EmailTemplate(company_id=company_id, **data.model_dump())
        self.db.add(template)
        await self.db.flush()
        await self.db.refresh(template)
        return template

    async def get_by_id(self, template_id: uuid.UUID, company_id: uuid.UUID) -> Optional[EmailTemplate]:
        result = await self.db.execute(
            select(EmailTemplate).where(
                EmailTemplate.id == template_id,
                EmailTemplate.company_id == company_id,
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        company_id: uuid.UUID,
        language: Optional[str] = None,
        type: Optional[str] = None,
    ) -> list[EmailTemplate]:
        query = select(EmailTemplate).where(EmailTemplate.company_id == company_id)
        if language:
            query = query.where(EmailTemplate.language == language)
        if type:
            query = query.where(EmailTemplate.type == type)
        query = query.order_by(EmailTemplate.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update(self, template: EmailTemplate, data: EmailTemplateUpdate) -> EmailTemplate:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(template, field, value)
        await self.db.flush()
        await self.db.refresh(template)
        return template

    async def delete(self, template: EmailTemplate) -> None:
        await self.db.delete(template)
        await self.db.flush()