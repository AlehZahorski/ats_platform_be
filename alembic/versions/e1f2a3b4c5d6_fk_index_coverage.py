"""Cover the remaining FK columns with btree indexes.

audit_szybkosci index-coverage scan found 13 foreign-key columns without an
index. Postgres does not auto-index FK columns (unlike MySQL InnoDB) — every
`DELETE` or `UPDATE` on the parent table has to sequential-scan the child
table to validate referential integrity. On a populated production database
this becomes the first visible bottleneck for "delete user", "delete
company" and reverse-lookup queries ("notes written by author X").

The 13 columns + the queries they unlock:

- application_stage_history.changed_by  — "stage changes by recruiter X"
- automation_rules.template_id          — automation fire (join email tpl)
- candidate_scores.recruiter_id         — "scores submitted by recruiter X"
- job_form_templates.template_id        — fetch job + its form template
- notes.author_id                       — "notes written by author X"
- review_assignments.assigned_by        — assignment audit trail
- saved_companies.company_id            — reverse lookup "candidates who
                                          saved company X"
- saved_jobs.job_id                     — reverse lookup "candidates who
                                          saved job X"
- search_logs.candidate_id              — search history per candidate
- tasks.created_by                      — tasks created by user X
- user_invitations.accepted_user_id     — who accepted this invitation
- user_invitations.invited_by           — invitations sent by user X
- work_schedules.updated_by             — audit "who edited the schedule"

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-05-29 16:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "d0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (index_name, table, column)
_FK_INDEXES = [
    ("ix_application_stage_history_changed_by", "application_stage_history", "changed_by"),
    ("ix_automation_rules_template_id", "automation_rules", "template_id"),
    ("ix_candidate_scores_recruiter_id", "candidate_scores", "recruiter_id"),
    ("ix_job_form_templates_template_id", "job_form_templates", "template_id"),
    ("ix_notes_author_id", "notes", "author_id"),
    ("ix_review_assignments_assigned_by", "review_assignments", "assigned_by"),
    ("ix_saved_companies_company_id", "saved_companies", "company_id"),
    ("ix_saved_jobs_job_id", "saved_jobs", "job_id"),
    ("ix_search_logs_candidate_id", "search_logs", "candidate_id"),
    ("ix_tasks_created_by", "tasks", "created_by"),
    ("ix_user_invitations_accepted_user_id", "user_invitations", "accepted_user_id"),
    ("ix_user_invitations_invited_by", "user_invitations", "invited_by"),
    ("ix_work_schedules_updated_by", "work_schedules", "updated_by"),
]


def upgrade() -> None:
    for name, table, col in _FK_INDEXES:
        # IF NOT EXISTS guard lets a partial earlier run be re-applied
        # cleanly. None of these are unique — pure foreign-key coverage.
        op.execute(f'CREATE INDEX IF NOT EXISTS "{name}" ON {table} ({col})')


def downgrade() -> None:
    for name, _, _ in _FK_INDEXES:
        op.execute(f'DROP INDEX IF EXISTS "{name}"')
