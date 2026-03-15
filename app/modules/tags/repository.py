from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.tags.models import ApplicationTag, Tag
from app.modules.tags.schemas import TagCreate


class TagRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, company_id: uuid.UUID, data: TagCreate) -> Tag:
        tag = Tag(company_id=company_id, name=data.name)
        self.db.add(tag)
        await self.db.flush()
        await self.db.refresh(tag)
        return tag

    async def list(self, company_id: uuid.UUID) -> list[Tag]:
        result = await self.db.execute(
            select(Tag).where(Tag.company_id == company_id).order_by(Tag.name)
        )
        return list(result.scalars().all())

    async def get_by_id(self, tag_id: uuid.UUID, company_id: uuid.UUID) -> Tag | None:
        result = await self.db.execute(
            select(Tag).where(Tag.id == tag_id, Tag.company_id == company_id)
        )
        return result.scalar_one_or_none()

    async def assign_tag(self, application_id: uuid.UUID, tag_id: uuid.UUID) -> None:
        existing = await self.db.execute(
            select(ApplicationTag).where(
                ApplicationTag.application_id == application_id,
                ApplicationTag.tag_id == tag_id,
            )
        )
        if existing.scalar_one_or_none():
            return  # already assigned
        link = ApplicationTag(application_id=application_id, tag_id=tag_id)
        self.db.add(link)
        await self.db.flush()

    async def remove_tag(self, application_id: uuid.UUID, tag_id: uuid.UUID) -> None:
        result = await self.db.execute(
            select(ApplicationTag).where(
                ApplicationTag.application_id == application_id,
                ApplicationTag.tag_id == tag_id,
            )
        )
        link = result.scalar_one_or_none()
        if link:
            await self.db.delete(link)
            await self.db.flush()

    async def get_application_tags(self, application_id: uuid.UUID) -> list[Tag]:
        result = await self.db.execute(
            select(Tag)
            .join(ApplicationTag, Tag.id == ApplicationTag.tag_id)
            .where(ApplicationTag.application_id == application_id)
        )
        return list(result.scalars().all())
