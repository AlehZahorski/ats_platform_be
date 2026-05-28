from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class AuditLog(BaseModel):
    __tablename__ = "audit_logs"
    # audit_database P1: every common audit query filters by company_id; the
    # bare `company_id` btree forces an in-memory sort on `created_at`. These
    # composite indexes let Postgres serve "last 100 events for company X"
    # straight from the index without sorting.
    __table_args__ = (
        Index("ix_audit_logs_company_created", "company_id", text("created_at DESC")),
        Index("ix_audit_logs_company_entity", "company_id", "entity_type", "entity_id"),
        Index("ix_audit_logs_company_action", "company_id", "action"),
        # audit_database P2: GIN for JSONB metadata filtering / search. The
        # column is `metadata` in the database (the Python attribute is
        # `metadata_` only because `metadata` is reserved by SQLAlchemy's
        # Declarative — we still index by the SQL name).
        Index("ix_audit_logs_metadata_gin", "metadata", postgresql_using="gin"),
    )

    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(Text)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    # audit_database P2/F-33: JSON → JSONB. Binary, indexable, supports `@>`.
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # audit_database P1/F-37: relationships used by the admin list view to
    # eager-load the actor and company. Default lazy="select" is intentional
    # — callers that don't paginate (e.g. background scripts) still work; the
    # list endpoint uses selectinload() in repository.list() to batch them.
    user: Mapped["User | None"] = relationship(foreign_keys=[user_id])  # noqa: F821
    company: Mapped["Company | None"] = relationship(foreign_keys=[company_id])  # noqa: F821
