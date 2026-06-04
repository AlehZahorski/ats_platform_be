from __future__ import annotations

import uuid

from app.core.base_service import BaseService
from app.core.exceptions import NotFoundError
from app.core.i18n import t
from app.modules.forms.models import FormField, FormTemplate
from app.modules.forms.repository import FormRepository
from app.modules.forms.schemas import FormFieldCreate, FormTemplateCreate, FormTemplateUpdate


class FormService(BaseService[FormRepository]):
    async def create_template(
        self, company_id: uuid.UUID, data: FormTemplateCreate
    ) -> FormTemplate:
        return await self.repository.create_template(company_id, data)

    async def get_template(self, template_id: uuid.UUID, company_id: uuid.UUID) -> FormTemplate:
        template = await self.repository.get_by_id_and_company(template_id, company_id)
        if not template:
            raise NotFoundError(t("forms.template_not_found"))
        return template

    async def list_templates(self, company_id: uuid.UUID) -> list[FormTemplate]:
        return await self.repository.list_by_company(company_id)

    async def update_template(
        self, template_id: uuid.UUID, company_id: uuid.UUID, data: FormTemplateUpdate
    ) -> FormTemplate:
        template = await self.get_template(template_id, company_id)
        return await self.repository.update(template, data)

    async def add_field(
        self, template_id: uuid.UUID, company_id: uuid.UUID, data: FormFieldCreate
    ) -> FormField:
        await self.get_template(template_id, company_id)
        return await self.repository.add_field(template_id, data)

    async def delete_field(
        self, template_id: uuid.UUID, field_id: uuid.UUID, company_id: uuid.UUID
    ) -> None:
        await self.get_template(template_id, company_id)
        field = await self.repository.get_field_by_id(field_id)
        # Confirm the field actually belongs to this (company-owned) template —
        # get_field_by_id loads by bare id, so without this check a field from
        # another template/company could be deleted via a matching template_id.
        if not field or field.template_id != template_id:
            raise NotFoundError(t("forms.field_not_found"))
        await self.repository.delete(field)
