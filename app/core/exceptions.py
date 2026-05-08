from __future__ import annotations


class DomainException(Exception):
    """Base class for all domain-level exceptions."""

    status_code: int = 500
    detail: str = "An unexpected error occurred."

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or self.__class__.detail
        super().__init__(self.detail)


class NotFoundError(DomainException):
    status_code = 404
    detail = "Resource not found."


class ConflictError(DomainException):
    status_code = 409
    detail = "Resource already exists."


class ForbiddenError(DomainException):
    status_code = 403
    detail = "You do not have permission to perform this action."


class UnauthorizedError(DomainException):
    status_code = 401
    detail = "Authentication required."


class UnprocessableError(DomainException):
    status_code = 422
    detail = "The provided data is invalid."


class ServiceUnavailableError(DomainException):
    status_code = 503
    detail = "An external service is temporarily unavailable."


class DuplicateDetectedError(ConflictError):
    """Raised when a duplicate candidate is detected on application submission."""

    def __init__(self, duplicate_response: object) -> None:
        self.duplicate_response = duplicate_response
        super().__init__("Duplicate candidate detected.")
