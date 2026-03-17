from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core.database import get_db
from app.core.dependencies import CurrentUser
from app.modules.users.schemas import UserRead

router = APIRouter()

SUPPORTED_LANGUAGES = {"en", "pl"}


class UserLanguageUpdate(BaseModel):
    language: str


@router.get("/me", response_model=UserRead)
async def get_me(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)


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
