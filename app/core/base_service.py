from __future__ import annotations

from abc import ABC
from typing import Generic, TypeVar

from app.core.base_repository import BaseRepository

RepoT = TypeVar("RepoT", bound=BaseRepository)


class BaseService(ABC, Generic[RepoT]):
    """Abstract base for all domain services.

    Subclasses declare their primary repository via __init__ and may
    inject additional repositories or services as needed:

        class TagService(BaseService[TagRepository]):
            def __init__(self, repository: TagRepository) -> None:
                super().__init__(repository)
    """

    def __init__(self, repository: RepoT) -> None:
        self.repository = repository
