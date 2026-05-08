from enum import StrEnum


class UserRole(StrEnum):
    owner = "owner"
    recruiter = "recruiter"
    manager = "manager"
