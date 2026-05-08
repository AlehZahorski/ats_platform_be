from enum import StrEnum


class CVParseStatus(StrEnum):
    queued = "queued"
    extracting = "extracting"
    parsing = "parsing"
    review_required = "review_required"
    completed = "completed"
    failed = "failed"


class ParsingStatus(StrEnum):
    idle = "idle"
    review_required = "review_required"
    completed = "completed"
    failed = "failed"


class BulkActionType(StrEnum):
    stage_change = "stage_change"
    reject = "reject"
    tag = "tag"
