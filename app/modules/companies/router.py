from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentCompany, CurrentUser
from app.modules.companies.repository import CompanyRepository
from app.modules.companies.schemas import CompanyRead, CompanyUpdate
from app.modules.companies.service import CompanyService

router = APIRouter()


def _get_service(db: AsyncSession = Depends(get_db)) -> CompanyService:
    return CompanyService(CompanyRepository(db))


@router.get("", response_model=CompanyRead)
async def get_company(company: CurrentCompany) -> CompanyRead:
    return CompanyRead.model_validate(company)


@router.patch("", response_model=CompanyRead)
async def update_company(
    data: CompanyUpdate,
    company: CurrentCompany,
    _user: CurrentUser,
    service: CompanyService = Depends(_get_service),
) -> CompanyRead:
    updated = await service.update(company, data)
    return CompanyRead.model_validate(updated)
