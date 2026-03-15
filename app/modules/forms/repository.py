from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.forms.models import FormField, FormTemplate
from app.modules.forms.schemas import FormFieldCreate, FormTemplateCreate, FormTemplateUpdate


class FormRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_template(self, company_id: uuid.UUID, data: FormTemplateCreate) -> FormTemplate:
        template = FormTemplate(company_id=company_id, name=data.name)
        self.db.add(template)
        await self.db.flush()

        for field_data in data.fields:
            field = FormField(template_id=template.id, **field_data.model_dump())
            self.db.add(field)

        await self.db.flush()
        await self.db.refresh(template)
        return await self._load(template.id)

    async def get_by_id(self, template_id: uuid.UUID, company_id: uuid.UUID) -> FormTemplate | None:
        return await self._load(template_id, company_id)

    async def list(self, company_id: uuid.UUID) -> list[FormTemplate]:
        result = await self.db.execute(
            select(FormTemplate)
            .where(FormTemplate.company_id == company_id)
            .options(selectinload(FormTemplate.fields))
            .order_by(FormTemplate.created_at.desc())
        )
        return list(result.scalars().all())

    async def update(self, template: FormTemplate, data: FormTemplateUpdate) -> FormTemplate:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(template, field, value)
        await self.db.flush()
        return await self._load(template.id)

    async def add_field(self, template_id: uuid.UUID, data: FormFieldCreate) -> FormField:
        field = FormField(template_id=template_id, **data.model_dump())
        self.db.add(field)
        await self.db.flush()
        await self.db.refresh(field)
        return field

    async def delete_field(self, field_id: uuid.UUID) -> None:
        result = await self.db.execute(select(FormField).where(FormField.id == field_id))
        field = result.scalar_one_or_none()
        if field:
            await self.db.delete(field)
            await self.db.flush()

    async def _load(self, template_id: uuid.UUID, company_id: uuid.UUID | None = None) -> FormTemplate | None:
        query = (
            select(FormTemplate)
            .where(FormTemplate.id == template_id)
            .options(selectinload(FormTemplate.fields))
        )
        if company_id:
            query = query.where(FormTemplate.company_id == company_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
