from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.enums.avatars import AvatarKey
from app.core.enums.users import UserRole


# -----------------------------------------------------------------------------
# Users
# -----------------------------------------------------------------------------
class UserBase(BaseModel):
    email: EmailStr
    role: UserRole = UserRole.recruiter


class UserCreate(UserBase):
    password: str


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    is_verified: bool
    is_active: bool = True
    language: str
    avatar_key: str | None = None
    created_at: datetime


class UserAvatarUpdate(BaseModel):
    avatar_key: AvatarKey | None = None


class UserRoleUpdate(BaseModel):
    # Owners cannot be assigned via this endpoint — only recruiter/manager.
    role: Literal[UserRole.recruiter, UserRole.manager]


class UserActiveUpdate(BaseModel):
    is_active: bool


class UserLanguageUpdate(BaseModel):
    language: str


# -----------------------------------------------------------------------------
# Invitations
# -----------------------------------------------------------------------------
class InvitationCreate(BaseModel):
    email: EmailStr
    role: Literal[UserRole.recruiter, UserRole.manager]


class InvitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    email: EmailStr
    role: UserRole
    invited_by: uuid.UUID | None
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
    # Only populated when the app runs in non-production mode — lets the owner copy
    # the link directly when SMTP is unavailable. Always None in production.
    invitation_url: str | None = None


class InvitationPreview(BaseModel):
    """Public preview shown on the accept-invitation page before the user sets a password."""
    email: EmailStr
    role: UserRole
    company_name: str
    expires_at: datetime


class AcceptInvitationRequest(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=128)
