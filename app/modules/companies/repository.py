from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.companies.models import Company
from app.modules.companies.schemas import CompanyCreate, CompanyUpdate


class CompanyRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, data: CompanyCreate) -> Company:
        company = Company(**data.model_dump())
        self.db.add(company)
        await self.db.flush()
        await self.db.refresh(company)
        return company

    async def get_by_id(self, company_id: uuid.UUID) -> Company | None:
        result = await self.db.execute(select(Company).where(Company.id == company_id))
        return result.scalar_one_or_none()

    async def update(self, company: Company, data: CompanyUpdate) -> Company:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(company, field, value)
        await self.db.flush()
        await self.db.refresh(company)
        return company
