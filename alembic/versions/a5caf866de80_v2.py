"""v2

Revision ID: a5caf866de80
Revises: 68bf88cadf2b
Create Date: 2026-03-17 22:32:39.442016

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a5caf866de80'
down_revision: Union[str, None] = '68bf88cadf2b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('consents',
    sa.Column('company_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('language', sa.Text(), nullable=False, server_default='en'),
    sa.Column('required', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_consents_company_id'), 'consents', ['company_id'], unique=False)

    op.create_table('email_templates',
    sa.Column('company_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('type', sa.Text(), nullable=False),
    sa.Column('subject', sa.Text(), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('language', sa.Text(), nullable=False, server_default='en'),
    sa.Column('variables', postgresql.JSON(astext_type=sa.Text()), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_email_templates_company_id'), 'email_templates', ['company_id'], unique=False)

    op.create_table('automation_rules',
    sa.Column('company_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('trigger_type', sa.Text(), nullable=False),
    sa.Column('trigger_value', sa.Text(), nullable=True),
    sa.Column('template_id', sa.UUID(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['template_id'], ['email_templates.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_automation_rules_company_id'), 'automation_rules', ['company_id'], unique=False)

    op.create_table('application_consents',
    sa.Column('application_id', sa.UUID(), nullable=False),
    sa.Column('consent_id', sa.UUID(), nullable=False),
    sa.Column('accepted', sa.Boolean(), nullable=False),
    sa.Column('accepted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['consent_id'], ['consents.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('application_id', 'consent_id')
    )
    op.create_index(op.f('ix_application_consents_consent_id'), 'application_consents', ['consent_id'], unique=False)

    op.create_table('application_events',
    sa.Column('application_id', sa.UUID(), nullable=False),
    sa.Column('company_id', sa.UUID(), nullable=True),
    sa.Column('event_type', sa.Text(), nullable=False),
    sa.Column('event_value', sa.Text(), nullable=True),
    sa.Column('metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_application_events_application_id'), 'application_events', ['application_id'], unique=False)
    op.create_index(op.f('ix_application_events_company_id'), 'application_events', ['company_id'], unique=False)

    op.create_table('interviews',
    sa.Column('application_id', sa.UUID(), nullable=False),
    sa.Column('recruiter_id', sa.UUID(), nullable=True),
    sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('duration_minutes', sa.Integer(), nullable=True),
    sa.Column('meeting_url', sa.Text(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['recruiter_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_interviews_application_id'), 'interviews', ['application_id'], unique=False)
    op.create_index(op.f('ix_interviews_recruiter_id'), 'interviews', ['recruiter_id'], unique=False)
    op.create_index(op.f('ix_interviews_scheduled_at'), 'interviews', ['scheduled_at'], unique=False)

    op.create_table('tasks',
    sa.Column('company_id', sa.UUID(), nullable=False),
    sa.Column('application_id', sa.UUID(), nullable=True),
    sa.Column('assigned_to', sa.UUID(), nullable=True),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('type', sa.Text(), nullable=True),
    sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed', sa.Boolean(), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['assigned_to'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_tasks_application_id'), 'tasks', ['application_id'], unique=False)
    op.create_index(op.f('ix_tasks_assigned_to'), 'tasks', ['assigned_to'], unique=False)
    op.create_index(op.f('ix_tasks_company_id'), 'tasks', ['company_id'], unique=False)

    # Extend existing tables
    op.add_column('applications', sa.Column('source', sa.Text(), nullable=True))
    op.add_column('applications', sa.Column('language', sa.Text(), nullable=False, server_default='en'))
    op.add_column('applications', sa.Column('data_retention_until', sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f('ix_applications_source'), 'applications', ['source'], unique=False)
    op.create_index(op.f('ix_applications_data_retention_until'), 'applications', ['data_retention_until'], unique=False)

    op.add_column('users', sa.Column('language', sa.Text(), nullable=False, server_default='en'))


def downgrade() -> None:
    op.drop_column('users', 'language')

    op.drop_index(op.f('ix_applications_data_retention_until'), table_name='applications')
    op.drop_index(op.f('ix_applications_source'), table_name='applications')
    op.drop_column('applications', 'data_retention_until')
    op.drop_column('applications', 'language')
    op.drop_column('applications', 'source')

    op.drop_index(op.f('ix_tasks_company_id'), table_name='tasks')
    op.drop_index(op.f('ix_tasks_assigned_to'), table_name='tasks')
    op.drop_index(op.f('ix_tasks_application_id'), table_name='tasks')
    op.drop_table('tasks')

    op.drop_index(op.f('ix_interviews_scheduled_at'), table_name='interviews')
    op.drop_index(op.f('ix_interviews_recruiter_id'), table_name='interviews')
    op.drop_index(op.f('ix_interviews_application_id'), table_name='interviews')
    op.drop_table('interviews')

    op.drop_index(op.f('ix_application_events_company_id'), table_name='application_events')
    op.drop_index(op.f('ix_application_events_application_id'), table_name='application_events')
    op.drop_table('application_events')

    op.drop_index(op.f('ix_application_consents_consent_id'), table_name='application_consents')
    op.drop_table('application_consents')

    op.drop_index(op.f('ix_automation_rules_company_id'), table_name='automation_rules')
    op.drop_table('automation_rules')

    op.drop_index(op.f('ix_email_templates_company_id'), table_name='email_templates')
    op.drop_table('email_templates')

    op.drop_index(op.f('ix_consents_company_id'), table_name='consents')
    op.drop_table('consents')