from __future__ import annotations

from typing import Generic, TypeVar

from app.core.base_repository import BaseRepository

RepoT = TypeVar("RepoT", bound=BaseRepository)


# M8 (audit_backend_code): dropped `ABC` — there was no `@abstractmethod`, so
# `ABC` only added metaclass overhead without enforcing any contract. The
# base is purely a typed Generic holder for the primary repository.
class BaseService(Generic[RepoT]):
    """Generic base for all domain services.

    Subclasses declare their primary repository via __init__ and may
    inject additional repositories or services as needed:

        class TagService(BaseService[TagRepository]):
            def __init__(self, repository: TagRepository) -> None:
                super().__init__(repository)
    """

    def __init__(self, repository: RepoT) -> None:
        self.repository = repository
