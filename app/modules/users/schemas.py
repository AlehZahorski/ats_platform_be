from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from app.core.enums.users import UserRole


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
    language: str
    created_at: datetime


class UserUpdate(BaseModel):
    role: UserRole | None = None


class UserLanguageUpdate(BaseModel):
    language: str
