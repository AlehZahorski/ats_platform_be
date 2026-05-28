from __future__ import annotations

import uuid

from app.core.base_service import BaseService
from app.core.exceptions import NotFoundError
from app.core.i18n import t
from app.modules.tags.models import Tag
from app.modules.tags.repository import TagRepository
from app.modules.tags.schemas import TagCreate


class TagService(BaseService[TagRepository]):

    async def create(self, company_id: uuid.UUID, data: TagCreate) -> Tag:
        return await self.repository.create(company_id, data)

    async def list_by_company(self, company_id: uuid.UUID) -> list[Tag]:
        return await self.repository.list_by_company(company_id)

    async def delete(self, tag_id: uuid.UUID, company_id: uuid.UUID) -> None:
        tag = await self.repository.get_by_id_and_company(tag_id, company_id)
        if not tag:
            raise NotFoundError(t("tags.not_found"))
        await self.repository.delete(tag)

    async def assign_tag(self, application_id: uuid.UUID, tag_id: uuid.UUID, company_id: uuid.UUID) -> None:
        tag = await self.repository.get_by_id_and_company(tag_id, company_id)
        if not tag:
            raise NotFoundError(t("tags.not_found"))
        await self.repository.assign_tag(application_id, tag_id)

    async def remove_tag(self, application_id: uuid.UUID, tag_id: uuid.UUID) -> None:
        await self.repository.remove_tag(application_id, tag_id)

    async def get_application_tags(self, application_id: uuid.UUID) -> list[Tag]:
        return await self.repository.get_application_tags(application_id)
