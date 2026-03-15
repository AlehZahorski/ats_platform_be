from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr


class UserBase(BaseModel):
    email: EmailStr
    role: Literal["owner", "recruiter", "manager"] = "recruiter"


class UserCreate(UserBase):
    password: str


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    is_verified: bool
    created_at: datetime


class UserUpdate(BaseModel):
    role: Literal["owner", "recruiter", "manager"] | None = None
