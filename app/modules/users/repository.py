from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.base_repository import BaseRepository
from app.core.enums.users import UserRole
from app.modules.users.models import RefreshToken, User, UserInvitation


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

    async def list_by_company(
        self, company_id: uuid.UUID, role: UserRole | None = None
    ) -> list[User]:
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


class InvitationRepository(BaseRepository[UserInvitation]):
    model = UserInvitation

    async def create(
        self,
        *,
        company_id: uuid.UUID,
        email: str,
        role: UserRole,
        token_hash: str,
        invited_by: uuid.UUID,
        expires_at: datetime,
    ) -> UserInvitation:
        invitation = UserInvitation(
            company_id=company_id,
            email=email,
            role=role,
            token_hash=token_hash,
            invited_by=invited_by,
            expires_at=expires_at,
        )
        self.db.add(invitation)
        await self.db.flush()
        return invitation

    async def get_active_by_email(self, company_id: uuid.UUID, email: str) -> UserInvitation | None:
        """Active = not accepted, not revoked, not expired."""
        now = datetime.now(UTC)
        result = await self.db.execute(
            select(UserInvitation).where(
                UserInvitation.company_id == company_id,
                UserInvitation.email == email,
                UserInvitation.accepted_at.is_(None),
                UserInvitation.revoked_at.is_(None),
                UserInvitation.expires_at > now,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_token_hash(self, token_hash: str) -> UserInvitation | None:
        result = await self.db.execute(
            select(UserInvitation).where(UserInvitation.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def list_pending_by_company(self, company_id: uuid.UUID) -> list[UserInvitation]:
        """Pending = not yet consumed (accepted_at IS NULL AND revoked_at IS NULL).
        Expired invitations are still returned so the owner can see and re-send them."""
        result = await self.db.execute(
            select(UserInvitation)
            .where(
                UserInvitation.company_id == company_id,
                UserInvitation.accepted_at.is_(None),
                UserInvitation.revoked_at.is_(None),
            )
            .order_by(UserInvitation.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_token(
        self,
        invitation: UserInvitation,
        *,
        token_hash: str,
        expires_at: datetime,
    ) -> UserInvitation:
        invitation.token_hash = token_hash
        invitation.expires_at = expires_at
        await self.db.flush()
        return invitation

    async def mark_accepted(self, invitation: UserInvitation, user_id: uuid.UUID) -> UserInvitation:
        invitation.accepted_at = datetime.now(UTC)
        invitation.accepted_user_id = user_id
        await self.db.flush()
        return invitation

    async def revoke(self, invitation: UserInvitation) -> UserInvitation:
        invitation.revoked_at = datetime.now(UTC)
        await self.db.flush()
        return invitation
