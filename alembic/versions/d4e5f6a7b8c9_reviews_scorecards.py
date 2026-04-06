"""reviews and scorecards

Revision ID: d4e5f6a7b8c9
Revises: c1d2e3f4a5b6
Create Date: 2026-04-05 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scorecard_templates",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_scorecard_templates_company_id"), "scorecard_templates", ["company_id"], unique=False)

    op.create_table(
        "scorecard_criteria",
        sa.Column("template_id", sa.UUID(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("max_score", sa.Integer(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["template_id"], ["scorecard_templates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_scorecard_criteria_template_id"), "scorecard_criteria", ["template_id"], unique=False)

    op.create_table(
        "review_assignments",
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("reviewer_id", sa.UUID(), nullable=False),
        sa.Column("assigned_by", sa.UUID(), nullable=True),
        sa.Column("template_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("overall_comment", sa.Text(), nullable=True),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["scorecard_templates.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("application_id", "reviewer_id", name="uq_review_assignments_application_reviewer"),
    )
    op.create_index(op.f("ix_review_assignments_application_id"), "review_assignments", ["application_id"], unique=False)
    op.create_index(op.f("ix_review_assignments_reviewer_id"), "review_assignments", ["reviewer_id"], unique=False)
    op.create_index(op.f("ix_review_assignments_template_id"), "review_assignments", ["template_id"], unique=False)

    op.create_table(
        "review_responses",
        sa.Column("assignment_id", sa.UUID(), nullable=False),
        sa.Column("criterion_id", sa.UUID(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["assignment_id"], ["review_assignments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["criterion_id"], ["scorecard_criteria.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assignment_id", "criterion_id", name="uq_review_responses_assignment_criterion"),
    )
    op.create_index(op.f("ix_review_responses_assignment_id"), "review_responses", ["assignment_id"], unique=False)
    op.create_index(op.f("ix_review_responses_criterion_id"), "review_responses", ["criterion_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_review_responses_criterion_id"), table_name="review_responses")
    op.drop_index(op.f("ix_review_responses_assignment_id"), table_name="review_responses")
    op.drop_table("review_responses")

    op.drop_index(op.f("ix_review_assignments_template_id"), table_name="review_assignments")
    op.drop_index(op.f("ix_review_assignments_reviewer_id"), table_name="review_assignments")
    op.drop_index(op.f("ix_review_assignments_application_id"), table_name="review_assignments")
    op.drop_table("review_assignments")

    op.drop_index(op.f("ix_scorecard_criteria_template_id"), table_name="scorecard_criteria")
    op.drop_table("scorecard_criteria")

    op.drop_index(op.f("ix_scorecard_templates_company_id"), table_name="scorecard_templates")
    op.drop_table("scorecard_templates")
