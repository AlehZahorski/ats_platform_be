from __future__ import annotations

from app.core.base_service import BaseService
from app.core.exceptions import ConflictError, UnprocessableError
from app.modules.companies.models import Company
from app.modules.companies.repository import CompanyRepository
from app.modules.companies.schemas import CompanyCreate, CompanyUpdate


class CompanyService(BaseService[CompanyRepository]):
    async def create(self, data: CompanyCreate) -> Company:
        return await self.repository.create(data)

    async def update(self, company: Company, data: CompanyUpdate) -> Company:
        """Apply edits to the owner's company. Two extra rules beyond
        the generic repository write:

          • Slug is set-once. Once a company has a public URL we can't
            silently change it — would 404 every bookmark and outbound
            link. To rename, a platform admin has to do it directly.
          • Slug must be globally unique. We check before persisting so
            the API returns a clean 409 instead of a DB integrity error.
        """
        if data.slug is not None:
            if company.slug and data.slug != company.slug:
                raise UnprocessableError(
                    "Adres URL firmy nie może być zmieniony po jego ustawieniu. "
                    "Skontaktuj się z administratorem, jeśli musi zostać zmieniony."
                )
            if not company.slug:
                taken_by = await self.repository.find_by_slug(data.slug)
                if taken_by and taken_by.id != company.id:
                    raise ConflictError("Ten adres URL firmy jest już zajęty.")

        return await self.repository.update(company, data)
