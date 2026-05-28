"""articles + newsletter_subscribers — Poradnik content + email signups

  - articles                — published guide articles (HTML content,
    denormalised author snapshot, category, featured flag)
  - newsletter_subscribers  — email list collected from the Poradnik
    newsletter widget (no sending pipeline yet, just storage)

Author info is snapshotted on the article row (name / role / avatar)
rather than joined off `users`, so deleting an account never blanks
out historical bylines and so external/guest contributors don't need
real user accounts.

Revision ID: f4a5b6c7d8e9
Revises: f3a4b5c6d7e8
Create Date: 2026-05-24 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f4a5b6c7d8e9"
down_revision: Union[str, None] = "f3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── articles ─────────────────────────────────────────────────────
    op.create_table(
        "articles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),  # HTML
        sa.Column("cover_image_url", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("is_featured", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.true()),
        # Author snapshot — denormalised so user deletions don't blank out bylines.
        sa.Column("author_name", sa.Text(), nullable=False),
        sa.Column("author_role", sa.Text(), nullable=True),
        sa.Column("author_avatar_url", sa.Text(), nullable=True),
        sa.Column("read_time_minutes", sa.Integer(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("slug", name="uq_articles_slug"),
    )
    op.create_index("ix_articles_category", "articles", ["category"])
    op.create_index("ix_articles_is_published", "articles", ["is_published"])
    op.create_index("ix_articles_is_featured", "articles", ["is_featured"])
    op.create_index("ix_articles_published_at", "articles", ["published_at"])

    # ── newsletter_subscribers ───────────────────────────────────────
    op.create_table(
        "newsletter_subscribers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=True),  # e.g. "poradnik" — drives basic attribution
        sa.Column("subscribed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("unsubscribed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("email", name="uq_newsletter_subscribers_email"),
    )


def downgrade() -> None:
    op.drop_table("newsletter_subscribers")

    op.drop_index("ix_articles_published_at", table_name="articles")
    op.drop_index("ix_articles_is_featured", table_name="articles")
    op.drop_index("ix_articles_is_published", table_name="articles")
    op.drop_index("ix_articles_category", table_name="articles")
    op.drop_table("articles")
