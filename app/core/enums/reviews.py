from enum import StrEnum


class ReviewStatus(StrEnum):
    pending = "pending"
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"
