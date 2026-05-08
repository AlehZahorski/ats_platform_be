from __future__ import annotations

import uuid

from app.core.base_service import BaseService
from app.core.enums.users import UserRole
from app.core.exceptions import UnprocessableError
from app.modules.users.models import User
from app.modules.users.repository import UserRepository

SUPPORTED_LANGUAGES: frozenset[str] = frozenset({"en", "pl"})


class UserService(BaseService[UserRepository]):

    async def list_by_company(self, company_id: uuid.UUID, role: UserRole | None = None) -> list[User]:
        return await self.repository.list_by_company(company_id, role)

    async def update_language(self, user: User, language: str) -> User:
        if language not in SUPPORTED_LANGUAGES:
            raise UnprocessableError(
                f"Unsupported language. Supported: {sorted(SUPPORTED_LANGUAGES)}"
            )
        user.language = language
        await self.repository.db.flush()
        return user
