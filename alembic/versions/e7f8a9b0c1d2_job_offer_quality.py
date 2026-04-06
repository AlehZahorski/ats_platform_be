"""job offer quality

Revision ID: e7f8a9b0c1d2
Revises: d4e5f6a7b8c9
Create Date: 2026-04-05 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("role_summary", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("role_purpose", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("responsibilities", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("jobs", sa.Column("must_haves", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("jobs", sa.Column("nice_to_haves", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("jobs", sa.Column("tech_stack", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("jobs", sa.Column("domain_context", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("seniority", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("experience_min_years", sa.Integer(), nullable=True))
    op.add_column("jobs", sa.Column("experience_max_years", sa.Integer(), nullable=True))
    op.add_column("jobs", sa.Column("work_mode", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("remote_constraints", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("success_profile", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("team_context", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("reporting_to", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("value_proposition", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("benefits", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("jobs", sa.Column("hiring_process", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("jobs", sa.Column("salary_min", sa.Integer(), nullable=True))
    op.add_column("jobs", sa.Column("salary_max", sa.Integer(), nullable=True))
    op.add_column("jobs", sa.Column("salary_currency", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("salary_period", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("contract_type", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "contract_type")
    op.drop_column("jobs", "salary_period")
    op.drop_column("jobs", "salary_currency")
    op.drop_column("jobs", "salary_max")
    op.drop_column("jobs", "salary_min")
    op.drop_column("jobs", "hiring_process")
    op.drop_column("jobs", "benefits")
    op.drop_column("jobs", "value_proposition")
    op.drop_column("jobs", "reporting_to")
    op.drop_column("jobs", "team_context")
    op.drop_column("jobs", "success_profile")
    op.drop_column("jobs", "remote_constraints")
    op.drop_column("jobs", "work_mode")
    op.drop_column("jobs", "experience_max_years")
    op.drop_column("jobs", "experience_min_years")
    op.drop_column("jobs", "seniority")
    op.drop_column("jobs", "domain_context")
    op.drop_column("jobs", "tech_stack")
    op.drop_column("jobs", "nice_to_haves")
    op.drop_column("jobs", "must_haves")
    op.drop_column("jobs", "responsibilities")
    op.drop_column("jobs", "role_purpose")
    op.drop_column("jobs", "role_summary")
