from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.admins.models import Admin, AdminRefreshToken


class AdminRepository:
    """Thin DAO over the two admin tables. No business logic — the
    auth service composes calls into login/logout/refresh flows."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_email(self, email: str) -> Admin | None:
        result = await self.db.execute(select(Admin).where(Admin.email == email.lower()))
        return result.scalar_one_or_none()

    async def get_by_id(self, admin_id: uuid.UUID) -> Admin | None:
        result = await self.db.execute(select(Admin).where(Admin.id == admin_id))
        return result.scalar_one_or_none()

    async def touch_last_login(self, admin: Admin) -> None:
        admin.last_login_at = datetime.now(timezone.utc)
        await self.db.flush()

    async def save_refresh_token(self, admin_id: uuid.UUID, token_hash: str, expires_at: datetime) -> None:
        self.db.add(AdminRefreshToken(admin_id=admin_id, token_hash=token_hash, expires_at=expires_at))
        await self.db.flush()

    async def get_refresh(self, token_hash: str) -> AdminRefreshToken | None:
        result = await self.db.execute(
            select(AdminRefreshToken).where(
                AdminRefreshToken.token_hash == token_hash,
                AdminRefreshToken.revoked.is_(False),
                AdminRefreshToken.expires_at > datetime.now(timezone.utc),
            )
        )
        return result.scalar_one_or_none()

    async def revoke_refresh(self, token_hash: str) -> None:
        await self.db.execute(
            update(AdminRefreshToken)
            .where(AdminRefreshToken.token_hash == token_hash)
            .values(revoked=True)
        )
