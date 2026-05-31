from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from datetime import date as date_t
from typing import Literal

from app.core.base_service import BaseService
from app.core.enums.organizer import ScheduleStatus
from app.core.enums.users import UserRole
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.i18n import t
from app.modules.organizer.models import WorkSchedule
from app.modules.organizer.repository import OrganizerRepository
from app.modules.organizer.schemas import (
    BoardResponse,
    DayAggregate,
    DayResponse,
    DayTask,
    EmployeeRow,
    EmployeeSummary,
    ScheduleOut,
    ScheduleUpsert,
    TaskAuthor,
)
from app.modules.users.models import User


def is_manager(user: User) -> bool:
    return user.role in (UserRole.owner.value, UserRole.manager.value)


def week_range(week_start: date_t) -> tuple[date_t, date_t, list[date_t]]:
    # Normalize to Monday — accept any date in week, snap back to its Monday.
    monday = week_start - timedelta(days=week_start.weekday())
    days = [monday + timedelta(days=i) for i in range(7)]
    return monday, days[-1], days


class OrganizerService(BaseService[OrganizerRepository]):
    # -------------------------------------------------------------------
    # Visibility
    # -------------------------------------------------------------------
    def can_view(self, actor: User, target_user_id: uuid.UUID) -> bool:
        if is_manager(actor):
            return True
        return actor.id == target_user_id

    def can_edit_schedule(self, actor: User, target_user_id: uuid.UUID) -> bool:
        # recruiter: only self; manager/owner: any user in company
        if is_manager(actor):
            return True
        return actor.id == target_user_id

    # -------------------------------------------------------------------
    # Board (week aggregates)
    # -------------------------------------------------------------------
    async def get_board(
        self, actor: User, week_start: date_t, scope: Literal["self", "team"]
    ) -> BoardResponse:
        monday, sunday, days = week_range(week_start)

        # Recruiter is always forced to self scope.
        effective_scope: Literal["self", "team"] = scope
        if not is_manager(actor):
            effective_scope = "self"

        if effective_scope == "self":
            users = [actor]
        else:
            users = await self.repository.list_active_company_users(actor.company_id)

        user_ids = [u.id for u in users]
        schedules = await self.repository.list_schedules_in_range(
            actor.company_id, user_ids, monday, sunday
        )
        tasks = await self.repository.list_tasks_in_range(
            actor.company_id, user_ids, monday, sunday
        )

        sched_idx: dict[tuple[uuid.UUID, date_t], WorkSchedule] = {
            (s.user_id, s.date): s for s in schedules
        }
        # task counts per (user, day)
        now = datetime.now(UTC)
        task_idx: dict[tuple[uuid.UUID, date_t], dict[str, int]] = defaultdict(
            lambda: {"total": 0, "done": 0, "overdue": 0}
        )
        for task in tasks:
            if not task.due_date or not task.assigned_to:
                continue
            key = (task.assigned_to, task.due_date.date())
            stats = task_idx[key]
            stats["total"] += 1
            if task.completed:
                stats["done"] += 1
            elif task.due_date < now:
                stats["overdue"] += 1

        rows: list[EmployeeRow] = []
        for u in users:
            day_aggs: list[DayAggregate] = []
            for d in days:
                sched = sched_idx.get((u.id, d))
                stats = task_idx.get((u.id, d), {"total": 0, "done": 0, "overdue": 0})
                day_aggs.append(
                    DayAggregate(
                        date=d,
                        status=ScheduleStatus(sched.status) if sched else None,
                        start_time=sched.start_time if sched else None,
                        end_time=sched.end_time if sched else None,
                        has_note=bool(sched and sched.note),
                        has_manager_note=bool(sched and sched.manager_note),
                        tasks_total=stats["total"],
                        tasks_done=stats["done"],
                        tasks_overdue=stats["overdue"],
                    )
                )
            rows.append(
                EmployeeRow(
                    user=EmployeeSummary.model_validate(u),
                    days=day_aggs,
                )
            )

        return BoardResponse(
            week_start=monday,
            week_end=sunday,
            scope=effective_scope,
            employees=rows,
        )

    # -------------------------------------------------------------------
    # Day detail
    # -------------------------------------------------------------------
    async def get_day(self, actor: User, target_user_id: uuid.UUID, day: date_t) -> DayResponse:
        if not self.can_view(actor, target_user_id):
            raise ForbiddenError(t("auth.role_not_permitted", role=actor.role))

        target = await self.repository.get_user(actor.company_id, target_user_id)
        if not target:
            raise NotFoundError(t("users.not_found"))

        sched_row = await self.repository.get_schedule(actor.company_id, target.id, day)
        tasks = await self.repository.list_tasks_for_user_day(actor.company_id, target.id, day)

        if sched_row:
            schedule = ScheduleOut(
                status=ScheduleStatus(sched_row.status),
                start_time=sched_row.start_time,
                end_time=sched_row.end_time,
                note=sched_row.note,
                manager_note=sched_row.manager_note,
                updated_by=EmployeeSummary.model_validate(sched_row.editor)
                if sched_row.editor
                else None,
                updated_at=sched_row.updated_at,
            )
        else:
            schedule = ScheduleOut()

        day_tasks = [
            DayTask(
                id=task.id,
                title=task.title,
                description=task.description,
                type=task.type,
                completed=task.completed,
                due_date=task.due_date,
                created_by=TaskAuthor.model_validate(task.creator) if task.creator else None,
            )
            for task in tasks
        ]

        return DayResponse(
            user=EmployeeSummary.model_validate(target),
            date=day,
            schedule=schedule,
            tasks=day_tasks,
        )

    # -------------------------------------------------------------------
    # Upsert schedule
    # -------------------------------------------------------------------
    async def upsert_schedule(self, actor: User, data: ScheduleUpsert) -> ScheduleOut:
        if not self.can_edit_schedule(actor, data.user_id):
            raise ForbiddenError(t("auth.role_not_permitted", role=actor.role))

        target = await self.repository.get_user(actor.company_id, data.user_id)
        if not target:
            raise NotFoundError(t("users.not_found"))

        sched = await self.repository.get_schedule(actor.company_id, target.id, data.date)
        if sched is None:
            sched = WorkSchedule(
                company_id=actor.company_id,
                user_id=target.id,
                date=data.date,
                status=data.status.value,
            )
            self.repository.db.add(sched)

        sched.status = data.status.value
        # Times only meaningful for work/remote; clear otherwise.
        if data.status in (ScheduleStatus.work, ScheduleStatus.remote):
            sched.start_time = data.start_time
            sched.end_time = data.end_time
        else:
            sched.start_time = None
            sched.end_time = None
        sched.note = data.note
        # Only managers can write manager_note. Recruiters: ignored (preserved).
        if is_manager(actor):
            sched.manager_note = data.manager_note
        sched.updated_by = actor.id

        await self.repository.db.flush()
        await self.repository.db.refresh(sched)

        editor = None
        if sched.updated_by:
            editor_user = await self.repository.get_user(actor.company_id, sched.updated_by)
            if editor_user:
                editor = EmployeeSummary.model_validate(editor_user)

        return ScheduleOut(
            status=ScheduleStatus(sched.status),
            start_time=sched.start_time,
            end_time=sched.end_time,
            note=sched.note,
            manager_note=sched.manager_note,
            updated_by=editor,
            updated_at=sched.updated_at,
        )
