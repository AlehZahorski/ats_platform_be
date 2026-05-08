from __future__ import annotations

from app.core.base_repository import BaseRepository
from app.modules.companies.models import Company
from app.modules.companies.schemas import CompanyCreate, CompanyUpdate


class CompanyRepository(BaseRepository[Company]):
    model = Company

    async def create(self, data: CompanyCreate) -> Company:
        company = Company(**data.model_dump())
        return await self.save(company)

    async def update(self, company: Company, data: CompanyUpdate) -> Company:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(company, field, value)
        await self.db.flush()
        await self.db.refresh(company)
        return company
