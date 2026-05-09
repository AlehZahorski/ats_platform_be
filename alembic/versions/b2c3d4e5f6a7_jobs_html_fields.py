"""jobs: convert 6 list[str] JSON fields to HTML Text

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-09 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None

_HTML_FIELDS = [
    "responsibilities",
    "must_haves",
    "nice_to_haves",
    "tech_stack",
    "benefits",
    "hiring_process",
]


def _json_array_to_html_list(col: str) -> str:
    """SQL expression that converts a JSON string[] column to an HTML <ul> list."""
    return f"""
        CASE
            WHEN {col} IS NULL OR {col}::text = '[]' THEN NULL
            ELSE (
                SELECT '<ul>' || string_agg('<li>' || elem || '</li>', '') || '</ul>'
                FROM jsonb_array_elements_text({col}::jsonb) AS elem
            )
        END
    """


def upgrade() -> None:
    for col in _HTML_FIELDS:
        tmp = f"{col}_html"
        # 1. add temp text column
        op.add_column("jobs", sa.Column(tmp, sa.Text(), nullable=True))
        # 2. populate using a plain UPDATE (subquery allowed here)
        op.execute(
            f"UPDATE jobs SET {tmp} = ({_json_array_to_html_list(col)})"
        )
        # 3. drop the old JSON column
        op.drop_column("jobs", col)
        # 4. rename temp column to original name
        op.alter_column("jobs", tmp, new_column_name=col)


def downgrade() -> None:
    for col in _HTML_FIELDS:
        tmp = f"{col}_json"
        op.add_column("jobs", sa.Column(tmp, sa.JSON(), nullable=True))
        op.execute(f"UPDATE jobs SET {tmp} = '[]'::json")
        op.drop_column("jobs", col)
        op.alter_column("jobs", tmp, new_column_name=col)
        op.alter_column("jobs", col, nullable=False, server_default="[]")
