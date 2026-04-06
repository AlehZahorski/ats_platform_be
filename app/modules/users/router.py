from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.core.database import get_db
from app.core.dependencies import CurrentCompany, CurrentUser
from app.modules.users.models import User
from app.modules.users.schemas import UserRead

router = APIRouter()

SUPPORTED_LANGUAGES = {"en", "pl"}


class UserLanguageUpdate(BaseModel):
    language: str


@router.get("/me", response_model=UserRead)
async def get_me(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)


@router.get("", response_model=list[UserRead])
async def list_users(
    company: CurrentCompany,
    _current_user: CurrentUser,
    role: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> list[UserRead]:
    query = select(User).where(User.company_id == company.id)
    if role:
        query = query.where(User.role == role)
    result = await db.execute(query.order_by(User.created_at.asc()))
    return [UserRead.model_validate(user) for user in result.scalars().all()]


@router.patch("/me/language")
async def update_language(
    data: UserLanguageUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> dict:
    if data.language not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported language. Supported: {sorted(SUPPORTED_LANGUAGES)}"
        )
    current_user.language = data.language
    await db.flush()
    return {"language": data.language}
