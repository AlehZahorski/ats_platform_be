from __future__ import annotations

from sqlalchemy import select

from app.core.base_repository import BaseRepository
from app.modules.companies.models import Company
from app.modules.companies.schemas import CompanyCreate, CompanyUpdate


class CompanyRepository(BaseRepository[Company]):
    model = Company

    async def create(self, data: CompanyCreate) -> Company:
        company = Company(**data.model_dump())
        return await self.save(company)

    async def update(self, company: Company, data: CompanyUpdate) -> Company:
        # exclude_unset=True so partial section saves don't overwrite untouched
        # JSONB fields with null. Section payloads (HowWeWorkCard etc.) come
        # back as pydantic objects — convert to plain dicts before assignment.
        payload = data.model_dump(exclude_unset=True)
        for field, value in payload.items():
            setattr(company, field, value)
        await self.db.flush()
        await self.db.refresh(company)
        return company

    async def find_by_slug(self, slug: str) -> Company | None:
        result = await self.db.execute(select(Company).where(Company.slug == slug))
        return result.scalar_one_or_none()
