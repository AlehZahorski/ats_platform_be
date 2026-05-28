from enum import StrEnum


class ScheduleStatus(StrEnum):
    work = "work"
    remote = "remote"
    vacation = "vacation"
    sick = "sick"
    off = "off"
