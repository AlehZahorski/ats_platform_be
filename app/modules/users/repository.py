from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base_repository import BaseRepository
from app.core.enums.users import UserRole
from app.modules.users.models import RefreshToken, User


class UserRepository(BaseRepository[User]):
    model = User

    async def create(
        self,
        company_id: uuid.UUID,
        email: str,
        password_hash: str,
        role: UserRole = UserRole.recruiter,
        is_verified: bool = False,
    ) -> User:
        user = User(
            company_id=company_id,
            email=email,
            password_hash=password_hash,
            role=role,
            is_verified=is_verified,
        )
        return await self.save(user)

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def list_by_company(self, company_id: uuid.UUID, role: UserRole | None = None) -> list[User]:
        query = select(User).where(User.company_id == company_id)
        if role:
            query = query.where(User.role == role)
        result = await self.db.execute(query.order_by(User.created_at.asc()))
        return list(result.scalars().all())

    async def verify(self, user: User) -> User:
        user.is_verified = True
        await self.db.flush()
        return user

    # ------------------------------------------------------------------
    # Refresh tokens
    # ------------------------------------------------------------------
    async def save_refresh_token(
        self,
        user_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> RefreshToken:
        token = RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        self.db.add(token)
        await self.db.flush()
        return token

    async def get_refresh_token(self, token_hash: str) -> RefreshToken | None:
        result = await self.db.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked.is_(False),
                RefreshToken.expires_at > datetime.now(UTC),
            )
        )
        return result.scalar_one_or_none()

    async def revoke_refresh_token(self, token: RefreshToken) -> None:
        token.revoked = True
        await self.db.flush()

    async def revoke_all_user_tokens(self, user_id: uuid.UUID) -> None:
        result = await self.db.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked.is_(False),
            )
        )
        for token in result.scalars().all():
            token.revoked = True
        await self.db.flush()
