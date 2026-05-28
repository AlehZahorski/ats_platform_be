import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import CurrentCompany, CurrentUser, OwnerOnly
from app.core.enums.users import UserRole
from app.modules.companies.repository import CompanyRepository
from app.modules.users.models import UserInvitation
from app.modules.users.repository import InvitationRepository, UserRepository
from app.modules.users.schemas import (
    InvitationCreate,
    InvitationRead,
    UserActiveUpdate,
    UserAvatarUpdate,
    UserLanguageUpdate,
    UserRead,
    UserRoleUpdate,
)
from app.modules.users.service import InvitationService, UserService


def _invitation_to_response(invitation: UserInvitation, raw_token: str | None = None) -> InvitationRead:
    """Attach the raw invitation URL only in non-production environments so the owner
    can copy the link when SMTP isn't configured. Never expose tokens in prod."""
    payload = InvitationRead.model_validate(invitation)
    if raw_token and not settings.is_production:
        payload.invitation_url = f"{settings.frontend_url}/accept-invitation?token={raw_token}"
    return payload

router = APIRouter()


def _user_service(db: AsyncSession = Depends(get_db)) -> UserService:
    return UserService(UserRepository(db))


def _invitation_service(db: AsyncSession = Depends(get_db)) -> InvitationService:
    return InvitationService(
        InvitationRepository(db),
        UserRepository(db),
        CompanyRepository(db),
    )


# ---------------------------------------------------------------------------
# Profile / self
# ---------------------------------------------------------------------------
@router.get("/me", response_model=UserRead)
async def get_me(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)


@router.patch("/me/language")
async def update_language(
    data: UserLanguageUpdate,
    current_user: CurrentUser,
    service: UserService = Depends(_user_service),
) -> dict:
    user = await service.update_language(current_user, data.language)
    return {"language": user.language}


@router.patch("/me/avatar", response_model=UserRead)
async def update_avatar(
    data: UserAvatarUpdate,
    current_user: CurrentUser,
    service: UserService = Depends(_user_service),
) -> UserRead:
    avatar_value = data.avatar_key.value if data.avatar_key else None
    user = await service.update_avatar(current_user, avatar_value)
    return UserRead.model_validate(user)


# ---------------------------------------------------------------------------
# Team — anyone authenticated can list members
# ---------------------------------------------------------------------------
@router.get("", response_model=list[UserRead])
async def list_users(
    company: CurrentCompany,
    _user: CurrentUser,
    role: Optional[UserRole] = None,
    service: UserService = Depends(_user_service),
) -> list[UserRead]:
    users = await service.list_by_company(company.id, role)
    return [UserRead.model_validate(u) for u in users]


# ---------------------------------------------------------------------------
# Team — owner-only management
# ---------------------------------------------------------------------------
@router.patch("/{user_id}/role", response_model=UserRead)
async def update_member_role(
    user_id: uuid.UUID,
    data: UserRoleUpdate,
    owner: OwnerOnly,
    service: UserService = Depends(_user_service),
) -> UserRead:
    user = await service.update_role(actor=owner, target_user_id=user_id, new_role=data.role)
    return UserRead.model_validate(user)


@router.patch("/{user_id}/active", response_model=UserRead)
async def update_member_active(
    user_id: uuid.UUID,
    data: UserActiveUpdate,
    owner: OwnerOnly,
    service: UserService = Depends(_user_service),
) -> UserRead:
    user = await service.set_active(actor=owner, target_user_id=user_id, is_active=data.is_active)
    return UserRead.model_validate(user)


# ---------------------------------------------------------------------------
# Invitations — owner-only
# ---------------------------------------------------------------------------
@router.post("/invitations", response_model=InvitationRead, status_code=status.HTTP_201_CREATED)
async def create_invitation(
    data: InvitationCreate,
    background_tasks: BackgroundTasks,
    owner: OwnerOnly,
    service: InvitationService = Depends(_invitation_service),
) -> InvitationRead:
    invitation, raw_token = await service.invite(
        actor=owner,
        email=data.email,
        role=data.role,
        background_tasks=background_tasks,
    )
    return _invitation_to_response(invitation, raw_token)


@router.get("/invitations", response_model=list[InvitationRead])
async def list_invitations(
    owner: OwnerOnly,
    service: InvitationService = Depends(_invitation_service),
) -> list[InvitationRead]:
    invitations = await service.list_pending(owner.company_id)
    return [InvitationRead.model_validate(i) for i in invitations]


@router.post("/invitations/{invitation_id}/resend", response_model=InvitationRead)
async def resend_invitation(
    invitation_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    owner: OwnerOnly,
    service: InvitationService = Depends(_invitation_service),
) -> InvitationRead:
    invitation, raw_token = await service.resend(
        actor=owner,
        invitation_id=invitation_id,
        background_tasks=background_tasks,
    )
    return _invitation_to_response(invitation, raw_token)


@router.delete("/invitations/{invitation_id}", response_model=InvitationRead)
async def revoke_invitation(
    invitation_id: uuid.UUID,
    owner: OwnerOnly,
    service: InvitationService = Depends(_invitation_service),
) -> InvitationRead:
    invitation = await service.revoke(actor=owner, invitation_id=invitation_id)
    return InvitationRead.model_validate(invitation)
