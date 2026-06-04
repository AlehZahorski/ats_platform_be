from enum import StrEnum


class ReviewStatus(StrEnum):
    # Lifecycle of a scorecard ASSIGNMENT (not the hiring decision — that lives
    # in ReviewAssignment.recommendation). Values must match the DB CHECK
    # constraint `ck_review_assignments_status` exactly. The old `approved` /
    # `rejected` members never existed in the DB CHECK (which allows `revoked`)
    # and were unused — they were a latent IntegrityError waiting to happen.
    pending = "pending"
    submitted = "submitted"
    revoked = "revoked"
