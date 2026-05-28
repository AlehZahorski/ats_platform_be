from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums.organizer import ScheduleStatus
from app.core.enums.users import UserRole


# -----------------------------------------------------------------------------
# Employee summary (compact card used in board)
# -----------------------------------------------------------------------------
class EmployeeSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: UserRole
    avatar_key: str | None = None


# -----------------------------------------------------------------------------
# Board (week view aggregates)
# -----------------------------------------------------------------------------
class DayAggregate(BaseModel):
    date: date
    status: ScheduleStatus | None = None
    start_time: time | None = None
    end_time: time | None = None
    has_note: bool = False
    has_manager_note: bool = False
    tasks_total: int = 0
    tasks_done: int = 0
    tasks_overdue: int = 0


class EmployeeRow(BaseModel):
    user: EmployeeSummary
    days: list[DayAggregate]


class BoardResponse(BaseModel):
    week_start: date
    week_end: date
    scope: Literal["self", "team"]
    employees: list[EmployeeRow]


# -----------------------------------------------------------------------------
# Day detail (modal)
# -----------------------------------------------------------------------------
class ScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: ScheduleStatus = ScheduleStatus.work
    start_time: time | None = None
    end_time: time | None = None
    note: str | None = None
    manager_note: str | None = None
    updated_by: EmployeeSummary | None = None
    updated_at: datetime | None = None


class TaskAuthor(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: UserRole
    avatar_key: str | None = None


class DayTask(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None = None
    type: str | None = None
    completed: bool
    due_date: datetime | None = None
    created_by: TaskAuthor | None = None


class DayResponse(BaseModel):
    user: EmployeeSummary
    date: date
    schedule: ScheduleOut
    tasks: list[DayTask]


# -----------------------------------------------------------------------------
# Mutations
# -----------------------------------------------------------------------------
class ScheduleUpsert(BaseModel):
    user_id: uuid.UUID
    date: date
    status: ScheduleStatus = ScheduleStatus.work
    start_time: time | None = None
    end_time: time | None = None
    note: str | None = Field(default=None, max_length=1000)
    # manager_note is silently ignored for non-managers in service layer
    manager_note: str | None = Field(default=None, max_length=1000)
