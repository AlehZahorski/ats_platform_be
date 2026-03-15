from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


JobStatus = Literal["draft", "open", "closed"]


class JobCreate(BaseModel):
    title: str
    description: str | None = None
    department: str | None = None
    location: str | None = None
    status: JobStatus = "draft"
    template_id: uuid.UUID | None = None


class JobUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    department: str | None = None
    location: str | None = None
    status: JobStatus | None = None


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    title: str
    description: str | None
    department: str | None
    location: str | None
    status: str
    created_at: datetime


class JobList(BaseModel):
    items: list[JobRead]
    total: int
