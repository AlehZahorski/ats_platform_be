from enum import StrEnum


class JobStatus(StrEnum):
    draft = "draft"
    open = "open"
    closed = "closed"


class WorkMode(StrEnum):
    remote = "remote"
    hybrid = "hybrid"
    onsite = "onsite"


class SalaryPeriod(StrEnum):
    hour = "hour"
    month = "month"
    year = "year"


class ContractType(StrEnum):
    b2b = "b2b"
    employment = "employment"
    contract = "contract"
    internship = "internship"
    temporary = "temporary"


class Seniority(StrEnum):
    junior = "junior"
    mid = "mid"
    senior = "senior"
    lead = "lead"
