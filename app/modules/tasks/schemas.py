from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.core.enums.tasks import TaskType


class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    type: Optional[TaskType] = None
    application_id: Optional[uuid.UUID] = None
    assigned_to: Optional[uuid.UUID] = None
    due_date: Optional[datetime] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    type: Optional[TaskType] = None
    application_id: Optional[uuid.UUID] = None
    assigned_to: Optional[uuid.UUID] = None
    due_date: Optional[datetime] = None
    completed: Optional[bool] = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    application_id: Optional[uuid.UUID]
    assigned_to: Optional[uuid.UUID]
    created_by: Optional[uuid.UUID]
    title: str
    description: Optional[str]
    type: Optional[TaskType]
    due_date: Optional[datetime]
    completed: bool
    completed_at: Optional[datetime]
    assignee: Optional[UserRead]
    creator: Optional[UserRead]
    created_at: datetime
    updated_at: datetime
