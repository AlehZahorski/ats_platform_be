from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class User(BaseModel):
    __tablename__ = "users"
    # audit_database P1/F-34: enforce the role enum at the DB layer so a stray
    # seed/SQL fix-up can't insert an unknown role. Pydantic validation alone
    # left the schema open to direct-SQL corruption.
    __table_args__ = (
        CheckConstraint(
            "role IN ('owner','recruiter','manager')",
            name="ck_users_role",
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # audit_database P3/F-36: UNIQUE already creates a btree index — the extra
    # `index=True` produced a duplicate. Drop it; the unique constraint covers
    # equality lookups.
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, default="recruiter")
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    language: Mapped[str] = mapped_column(Text, nullable=False, default="en")  # v2: i18n
    avatar_key: Mapped[str | None] = mapped_column(Text, nullable=True)

    # relationships
    company: Mapped[Company] = relationship(back_populates="users")  # noqa: F821
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )  # noqa: F821


class RefreshToken(BaseModel):
    __tablename__ = "refresh_tokens"
    # audit_database P3: session cleanup ("delete revoked tokens older than
    # N days") scans on (user_id, revoked, expires_at) — composite index
    # serves it without touching the heap.
    __table_args__ = (
        Index(
            "ix_refresh_tokens_user_revoked_expires",
            "user_id",
            "revoked",
            "expires_at",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # audit_database P3/F-36: UNIQUE already creates a btree — extra `index=True` dropped.
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    user: Mapped[User] = relationship(back_populates="refresh_tokens")


class UserInvitation(BaseModel):
    __tablename__ = "user_invitations"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
