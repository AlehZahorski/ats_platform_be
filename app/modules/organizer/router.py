import uuid
from datetime import date as date_t
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentUser
from app.modules.organizer.repository import OrganizerRepository
from app.modules.organizer.schemas import (
    BoardResponse,
    DayResponse,
    ScheduleOut,
    ScheduleUpsert,
)
from app.modules.organizer.service import OrganizerService

router = APIRouter()


def _service(db: AsyncSession = Depends(get_db)) -> OrganizerService:
    return OrganizerService(OrganizerRepository(db))


@router.get("/board", response_model=BoardResponse)
async def get_board(
    user: CurrentUser,
    week_start: date_t = Query(
        ..., description="Any date within the requested week; snapped to Monday."
    ),
    scope: Literal["self", "team"] = Query("team"),
    service: OrganizerService = Depends(_service),
) -> BoardResponse:
    return await service.get_board(user, week_start, scope)


@router.get("/day", response_model=DayResponse)
async def get_day(
    user: CurrentUser,
    user_id: uuid.UUID = Query(...),
    date: date_t = Query(...),
    service: OrganizerService = Depends(_service),
) -> DayResponse:
    return await service.get_day(user, user_id, date)


@router.put("/schedule", response_model=ScheduleOut)
async def upsert_schedule(
    data: ScheduleUpsert,
    user: CurrentUser,
    service: OrganizerService = Depends(_service),
) -> ScheduleOut:
    return await service.upsert_schedule(user, data)
