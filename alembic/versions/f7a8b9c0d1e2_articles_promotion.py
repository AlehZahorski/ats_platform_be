"""articles.is_promoted + promoted_until — promotion slots for company posts

Lets the admin lift a company-authored article into the editorial
/poradnik feed for a limited time. The public query becomes:

    WHERE is_published
      AND (
        type = 'editorial'
        OR (
          type = 'company'
          AND is_promoted = true
          AND (promoted_until IS NULL OR promoted_until > now())
        )
      )

`promoted_until` is the window expiry. NULL means promotion runs forever
(used when a company is on a permanent visibility plan). The boolean is
redundant strictly speaking — could be derived from `promoted_until` —
but keeping it explicit makes "unpromote" and indexing trivial.

Revision ID: f7a8b9c0d1e2
Revises: f6a7b8c9d0e1
Create Date: 2026-05-24 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "articles",
        sa.Column("is_promoted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "articles",
        sa.Column("promoted_until", sa.DateTime(timezone=True), nullable=True),
    )
    # Partial index — only promoted rows are interesting for the public
    # /poradnik query. Keeps the index tiny.
    op.create_index(
        "ix_articles_is_promoted",
        "articles",
        ["is_promoted"],
        postgresql_where=sa.text("is_promoted = true"),
    )


def downgrade() -> None:
    op.drop_index("ix_articles_is_promoted", table_name="articles")
    op.drop_column("articles", "promoted_until")
    op.drop_column("articles", "is_promoted")
