from fastapi import APIRouter

from app.core.dependencies import CurrentCompany, CurrentUser
from app.modules.companies.schemas import CompanyRead, CompanyUpdate
from app.modules.companies.repository import CompanyRepository
from app.core.database import get_db
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("", response_model=CompanyRead)
async def get_company(company: CurrentCompany) -> CompanyRead:
    return CompanyRead.model_validate(company)


@router.patch("", response_model=CompanyRead)
async def update_company(
    data: CompanyUpdate,
    company: CurrentCompany,
    db: AsyncSession = Depends(get_db),
) -> CompanyRead:
    repo = CompanyRepository(db)
    updated = await repo.update(company, data)
    return CompanyRead.model_validate(updated)
