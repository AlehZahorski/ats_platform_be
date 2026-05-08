from __future__ import annotations

from app.core.base_service import BaseService
from app.modules.companies.models import Company
from app.modules.companies.repository import CompanyRepository
from app.modules.companies.schemas import CompanyCreate, CompanyUpdate


class CompanyService(BaseService[CompanyRepository]):

    async def create(self, data: CompanyCreate) -> Company:
        return await self.repository.create(data)

    async def update(self, company: Company, data: CompanyUpdate) -> Company:
        return await self.repository.update(company, data)
