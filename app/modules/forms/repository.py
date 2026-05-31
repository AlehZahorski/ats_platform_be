from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.base_repository import BaseRepository
from app.modules.forms.models import FormField, FormTemplate
from app.modules.forms.schemas import FormFieldCreate, FormTemplateCreate, FormTemplateUpdate


class FormRepository(BaseRepository[FormTemplate]):
    model = FormTemplate

    async def create_template(
        self, company_id: uuid.UUID, data: FormTemplateCreate
    ) -> FormTemplate:
        template = FormTemplate(company_id=company_id, name=data.name)
        self.db.add(template)
        await self.db.flush()

        for field_data in data.fields:
            self.db.add(FormField(template_id=template.id, **field_data.model_dump()))

        await self.db.flush()
        return await self._load(template.id)

    async def get_by_id_and_company(
        self, template_id: uuid.UUID, company_id: uuid.UUID
    ) -> FormTemplate | None:
        return await self._load(template_id, company_id)

    async def list_by_company(self, company_id: uuid.UUID) -> list[FormTemplate]:
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
        return await self.save(field)

    async def get_field_by_id(self, field_id: uuid.UUID) -> FormField | None:
        result = await self.db.execute(select(FormField).where(FormField.id == field_id))
        return result.scalar_one_or_none()

    async def _load(
        self, template_id: uuid.UUID, company_id: uuid.UUID | None = None
    ) -> FormTemplate | None:
        query = (
            select(FormTemplate)
            .where(FormTemplate.id == template_id)
            .options(selectinload(FormTemplate.fields))
        )
        if company_id:
            query = query.where(FormTemplate.company_id == company_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
