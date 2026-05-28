"""articles.type + articles.company_id + articles.author_email

Adds the discriminator + ownership columns needed to host two flavours
of articles in one table:

  - type='editorial' — written by platform admins for /poradnik.
    company_id is NULL.
  - type='company'   — written by a verified company for /opinie-firm.
    company_id points at companies(id); the admin can moderate but
    doesn't own.

Single-table-with-type beats two tables here because:
  • content shape is identical (slug, title, content HTML, cover, …)
  • SEO patterns are identical (sitemap, JSON-LD)
  • Admin moderation surface is one list, not two

ON DELETE SET NULL on company_id so deleting a company doesn't wipe its
historical articles — they survive as orphaned brand content (admin can
clean up later if needed).

Revision ID: f6a7b8c9d0e1
Revises: f5a6b7c8d9e0
Create Date: 2026-05-24 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "f5a6b7c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "articles",
        sa.Column("type", sa.Text(), nullable=False, server_default="editorial"),
    )
    op.create_index("ix_articles_type", "articles", ["type"])

    op.add_column(
        "articles",
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_articles_company_id", "articles", ["company_id"])

    op.add_column("articles", sa.Column("author_email", sa.Text(), nullable=True))

    # No backfill needed — server_default='editorial' handles existing rows.


def downgrade() -> None:
    op.drop_column("articles", "author_email")
    op.drop_index("ix_articles_company_id", table_name="articles")
    op.drop_column("articles", "company_id")
    op.drop_index("ix_articles_type", table_name="articles")
    op.drop_column("articles", "type")
