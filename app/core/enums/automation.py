from enum import StrEnum


class AutomationTriggerType(StrEnum):
    stage_changed = "stage_changed"
    application_created = "application_created"
