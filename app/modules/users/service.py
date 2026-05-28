from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import BackgroundTasks, Response

from app.core.base_service import BaseService
from app.core.config import settings
from app.core.enums.users import UserRole
from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnprocessableError,
)
from app.core.i18n import t
from app.core.security import (
    access_token_cookie_max_age,
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_token,
)
from app.modules.companies.repository import CompanyRepository
from app.modules.users.models import User, UserInvitation
from app.modules.users.repository import InvitationRepository, UserRepository

SUPPORTED_LANGUAGES: frozenset[str] = frozenset({"en", "pl"})
INVITATION_TTL_DAYS = 7


class UserService(BaseService[UserRepository]):

    async def list_by_company(self, company_id: uuid.UUID, role: UserRole | None = None) -> list[User]:
        return await self.repository.list_by_company(company_id, role)

    async def update_language(self, user: User, language: str) -> User:
        if language not in SUPPORTED_LANGUAGES:
            raise UnprocessableError(
                t("users.unsupported_language", languages=sorted(SUPPORTED_LANGUAGES))
            )
        user.language = language
        await self.repository.db.flush()
        return user

    async def update_avatar(self, user: User, avatar_key: str | None) -> User:
        # AvatarKey enum is already validated at the schema layer.
        user.avatar_key = avatar_key
        await self.repository.db.flush()
        return user

    # ------------------------------------------------------------------
    # Team management (owner-only — guarded at router level)
    # ------------------------------------------------------------------
    async def get_member(self, company_id: uuid.UUID, user_id: uuid.UUID) -> User:
        user = await self.repository.get_by_id(user_id)
        if not user or user.company_id != company_id:
            raise NotFoundError(t("users.not_found"))
        return user

    async def update_role(
        self,
        *,
        actor: User,
        target_user_id: uuid.UUID,
        new_role: UserRole,
    ) -> User:
        target = await self.get_member(actor.company_id, target_user_id)

        if target.id == actor.id:
            raise ForbiddenError(t("users.cannot_modify_self"))
        if target.role == UserRole.owner:
            raise ForbiddenError(t("users.cannot_modify_owner"))
        if new_role == UserRole.owner:
            raise ForbiddenError(t("users.cannot_assign_owner"))

        target.role = new_role
        await self.repository.db.flush()
        return target

    async def set_active(
        self,
        *,
        actor: User,
        target_user_id: uuid.UUID,
        is_active: bool,
    ) -> User:
        target = await self.get_member(actor.company_id, target_user_id)

        if target.id == actor.id:
            raise ForbiddenError(t("users.cannot_modify_self"))
        if target.role == UserRole.owner:
            raise ForbiddenError(t("users.cannot_modify_owner"))

        target.is_active = is_active
        if not is_active:
            # Drop active sessions so the deactivated user is kicked out.
            await self.repository.revoke_all_user_tokens(target.id)
        await self.repository.db.flush()
        return target


class InvitationService(BaseService[InvitationRepository]):

    def __init__(
        self,
        repository: InvitationRepository,
        user_repo: UserRepository,
        company_repo: CompanyRepository,
    ) -> None:
        super().__init__(repository)
        self.user_repo = user_repo
        self.company_repo = company_repo

    # ------------------------------------------------------------------
    # Owner flow
    # ------------------------------------------------------------------
    async def invite(
        self,
        *,
        actor: User,
        email: str,
        role: UserRole,
        background_tasks: BackgroundTasks,
    ) -> tuple[UserInvitation, str]:
        if role not in (UserRole.recruiter, UserRole.manager):
            raise UnprocessableError(t("users.invitation.invalid_role"))

        email_norm = email.strip().lower()

        # Email taken globally (User.email is UNIQUE)
        if await self.user_repo.get_by_email(email_norm):
            raise ConflictError(t("users.invitation.email_taken"))

        # Active invitation already exists
        if await self.repository.get_active_by_email(actor.company_id, email_norm):
            raise ConflictError(t("users.invitation.already_pending"))

        raw_token, token_hash, expires_at = _new_token()
        invitation = await self.repository.create(
            company_id=actor.company_id,
            email=email_norm,
            role=role,
            token_hash=token_hash,
            invited_by=actor.id,
            expires_at=expires_at,
        )

        company = await self.company_repo.get_by_id(actor.company_id)
        await self._send_invitation_email(
            background_tasks=background_tasks,
            email=email_norm,
            raw_token=raw_token,
            invited_by_email=actor.email,
            company_name=company.name if company else settings.app_name,
            role=role,
        )
        return invitation, raw_token

    async def list_pending(self, company_id: uuid.UUID) -> list[UserInvitation]:
        return await self.repository.list_pending_by_company(company_id)

    async def resend(
        self,
        *,
        actor: User,
        invitation_id: uuid.UUID,
        background_tasks: BackgroundTasks,
    ) -> tuple[UserInvitation, str]:
        invitation = await self._get_pending(actor.company_id, invitation_id)

        raw_token, token_hash, expires_at = _new_token()
        invitation = await self.repository.update_token(
            invitation, token_hash=token_hash, expires_at=expires_at
        )

        company = await self.company_repo.get_by_id(actor.company_id)
        await self._send_invitation_email(
            background_tasks=background_tasks,
            email=invitation.email,
            raw_token=raw_token,
            invited_by_email=actor.email,
            company_name=company.name if company else settings.app_name,
            role=UserRole(invitation.role),
        )
        return invitation, raw_token

    async def revoke(self, *, actor: User, invitation_id: uuid.UUID) -> UserInvitation:
        invitation = await self._get_pending(actor.company_id, invitation_id)
        return await self.repository.revoke(invitation)

    # ------------------------------------------------------------------
    # Public flow (no auth)
    # ------------------------------------------------------------------
    async def preview(self, raw_token: str) -> tuple[UserInvitation, str]:
        invitation = await self._resolve_valid_invitation(raw_token)
        company = await self.company_repo.get_by_id(invitation.company_id)
        company_name = company.name if company else ""
        return invitation, company_name

    async def accept(
        self,
        *,
        raw_token: str,
        password: str,
        response: Response,
    ) -> User:
        invitation = await self._resolve_valid_invitation(raw_token)

        if await self.user_repo.get_by_email(invitation.email):
            # Edge case — someone snuck in a User with that email between invite and accept.
            raise ConflictError(t("users.invitation.email_taken"))

        user = await self.user_repo.create(
            company_id=invitation.company_id,
            email=invitation.email,
            password_hash=hash_password(password),
            role=UserRole(invitation.role),
            is_verified=True,
        )
        await self.repository.mark_accepted(invitation, user.id)

        # Auto-login — mirror AuthService.login token + cookie logic.
        access_token = create_access_token(
            subject=str(user.id),
            extra_claims={"company_id": str(user.company_id), "role": user.role},
        )
        raw_refresh, refresh_hash = create_refresh_token()
        refresh_expires = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
        await self.user_repo.save_refresh_token(user.id, refresh_hash, refresh_expires)
        _set_auth_cookies(response, access_token, raw_refresh)
        return user

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    async def _get_pending(self, company_id: uuid.UUID, invitation_id: uuid.UUID) -> UserInvitation:
        invitation = await self.repository.get_by_id(invitation_id)
        if not invitation or invitation.company_id != company_id:
            raise NotFoundError(t("users.invitation.not_found"))
        if invitation.accepted_at is not None:
            raise ConflictError(t("users.invitation.already_accepted"))
        if invitation.revoked_at is not None:
            raise ConflictError(t("users.invitation.revoked"))
        return invitation

    async def _resolve_valid_invitation(self, raw_token: str) -> UserInvitation:
        invitation = await self.repository.get_by_token_hash(hash_token(raw_token))
        if not invitation:
            raise NotFoundError(t("users.invitation.invalid_token"))
        if invitation.accepted_at is not None:
            raise ConflictError(t("users.invitation.already_accepted"))
        if invitation.revoked_at is not None:
            raise ConflictError(t("users.invitation.revoked"))
        if invitation.expires_at < datetime.now(UTC):
            raise ConflictError(t("users.invitation.expired"))
        return invitation

    async def _send_invitation_email(
        self,
        *,
        background_tasks: BackgroundTasks,
        email: str,
        raw_token: str,
        invited_by_email: str,
        company_name: str,
        role: UserRole,
    ) -> None:
        from app.services.mailer import mail_service

        invitation_url = f"{settings.frontend_url}/accept-invitation?token={raw_token}"
        try:
            mail_service.send_invitation_email(
                background_tasks,
                to_email=email,
                invitation_url=invitation_url,
                invited_by_email=invited_by_email,
                company_name=company_name,
                role=role.value,
            )
        except Exception:
            # Email delivery failure should not roll back the invitation — owner can resend.
            pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _new_token() -> tuple[str, str, datetime]:
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw), datetime.now(UTC) + timedelta(days=INVITATION_TTL_DAYS)


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    secure = settings.is_production
    response.set_cookie(
        "access_token", access_token,
        httponly=True, secure=secure, samesite="lax",
        max_age=access_token_cookie_max_age(),
    )
    response.set_cookie(
        "refresh_token", refresh_token,
        httponly=True, secure=secure, samesite="lax",
        max_age=settings.refresh_token_expire_days * 86400,
        path="/api/v1/auth/refresh",
    )
