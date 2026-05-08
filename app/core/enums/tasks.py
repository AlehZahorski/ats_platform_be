from enum import StrEnum


class TaskType(StrEnum):
    follow_up = "follow_up"
    reminder = "reminder"
    review = "review"
    call = "call"
