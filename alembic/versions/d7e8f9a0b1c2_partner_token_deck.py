"""partner_access_tokens.deck — choose which deck a token unlocks

Adds a `deck` column so an admin can mint a token for the investor pitch
deck or the partner/co-founder recruitment deck. The /prezentacja gate
serves the matching HTML.

Revision ID: d7e8f9a0b1c2
Revises: c6d7e8f9a0b1
Create Date: 2026-06-04 14:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d7e8f9a0b1c2"
down_revision: Union[str, None] = "c6d7e8f9a0b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "partner_access_tokens",
        sa.Column(
            "deck",
            sa.Text(),
            nullable=False,
            server_default="investor",
        ),
    )


def downgrade() -> None:
    op.drop_column("partner_access_tokens", "deck")
