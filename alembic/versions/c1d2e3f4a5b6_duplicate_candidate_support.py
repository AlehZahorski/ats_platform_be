"""duplicate candidate support

Revision ID: c1d2e3f4a5b6
Revises: a5caf866de80
Create Date: 2026-04-05 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "a5caf866de80"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("normalized_email", sa.Text(), nullable=True))
    op.add_column("applications", sa.Column("normalized_phone", sa.Text(), nullable=True))
    op.execute("UPDATE applications SET normalized_email = lower(trim(email)) WHERE normalized_email IS NULL")
    op.execute(
        "UPDATE applications SET normalized_phone = regexp_replace(phone, '\\D', '', 'g') "
        "WHERE phone IS NOT NULL AND normalized_phone IS NULL"
    )
    op.alter_column("applications", "normalized_email", existing_type=sa.Text(), nullable=False)
    op.create_index(op.f("ix_applications_normalized_email"), "applications", ["normalized_email"], unique=False)
    op.create_index(op.f("ix_applications_normalized_phone"), "applications", ["normalized_phone"], unique=False)

    op.create_table(
        "application_duplicate_links",
        sa.Column("source_application_id", sa.UUID(), nullable=False),
        sa.Column("duplicate_application_id", sa.UUID(), nullable=False),
        sa.Column("match_reasons", sa.JSON(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["duplicate_application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_application_duplicate_links_source_application_id"),
        "application_duplicate_links",
        ["source_application_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_application_duplicate_links_duplicate_application_id"),
        "application_duplicate_links",
        ["duplicate_application_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_application_duplicate_links_duplicate_application_id"),
        table_name="application_duplicate_links",
    )
    op.drop_index(
        op.f("ix_application_duplicate_links_source_application_id"),
        table_name="application_duplicate_links",
    )
    op.drop_table("application_duplicate_links")

    op.drop_index(op.f("ix_applications_normalized_phone"), table_name="applications")
    op.drop_index(op.f("ix_applications_normalized_email"), table_name="applications")
    op.drop_column("applications", "normalized_phone")
    op.drop_column("applications", "normalized_email")
