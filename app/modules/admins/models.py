from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Admin(BaseModel):
    """Platform-side administrator. Separate identity from `users`
    (recruiters) and `candidates` (job seekers). Logs in at /admin/login
    and gets a distinct cookie (`admin_access_token`) so multiple sessions
    can coexist in the same browser without confusion.
    """

    __tablename__ = "admins"

    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    refresh_tokens: Mapped[list[AdminRefreshToken]] = relationship(
        back_populates="admin", cascade="all, delete-orphan"
    )


class AdminRefreshToken(BaseModel):
    __tablename__ = "admin_refresh_tokens"

    admin_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admins.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    admin: Mapped[Admin] = relationship(back_populates="refresh_tokens")
