from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.enums.tasks import TaskType


class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    type: TaskType | None = None
    application_id: uuid.UUID | None = None
    assigned_to: uuid.UUID | None = None
    due_date: datetime | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    type: TaskType | None = None
    application_id: uuid.UUID | None = None
    assigned_to: uuid.UUID | None = None
    due_date: datetime | None = None
    completed: bool | None = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    application_id: uuid.UUID | None
    assigned_to: uuid.UUID | None
    created_by: uuid.UUID | None
    title: str
    description: str | None
    type: TaskType | None
    due_date: datetime | None
    completed: bool
    completed_at: datetime | None
    assignee: UserRead | None
    creator: UserRead | None
    created_at: datetime
    updated_at: datetime
