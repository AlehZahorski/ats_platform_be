from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentCompany, CurrentUser
from app.core.enums.users import UserRole
from app.modules.users.repository import UserRepository
from app.modules.users.schemas import UserLanguageUpdate, UserRead
from app.modules.users.service import UserService

router = APIRouter()


def _get_service(db: AsyncSession = Depends(get_db)) -> UserService:
    return UserService(UserRepository(db))


@router.get("/me", response_model=UserRead)
async def get_me(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)


@router.get("", response_model=list[UserRead])
async def list_users(
    company: CurrentCompany,
    _user: CurrentUser,
    role: Optional[UserRole] = None,
    service: UserService = Depends(_get_service),
) -> list[UserRead]:
    users = await service.list_by_company(company.id, role)
    return [UserRead.model_validate(u) for u in users]


@router.patch("/me/language")
async def update_language(
    data: UserLanguageUpdate,
    current_user: CurrentUser,
    service: UserService = Depends(_get_service),
) -> dict:
    user = await service.update_language(current_user, data.language)
    return {"language": user.language}
