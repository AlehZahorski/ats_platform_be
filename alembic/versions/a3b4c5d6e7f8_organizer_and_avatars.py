"""organizer module — work_schedules + users.avatar_key

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-05-21 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("avatar_key", sa.Text(), nullable=True),
    )

    op.create_table(
        "work_schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="work"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("manager_note", sa.Text(), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "date", name="uq_work_schedules_user_date"),
    )
    op.create_index("ix_work_schedules_company_date", "work_schedules", ["company_id", "date"])
    op.create_index("ix_work_schedules_user_date", "work_schedules", ["user_id", "date"])


def downgrade() -> None:
    op.drop_index("ix_work_schedules_user_date", table_name="work_schedules")
    op.drop_index("ix_work_schedules_company_date", table_name="work_schedules")
    op.drop_table("work_schedules")
    op.drop_column("users", "avatar_key")
