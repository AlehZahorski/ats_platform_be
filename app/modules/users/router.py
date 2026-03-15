from fastapi import APIRouter

from app.core.dependencies import CurrentUser
from app.modules.users.schemas import UserRead

router = APIRouter()


@router.get("/me", response_model=UserRead)
async def get_me(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)
