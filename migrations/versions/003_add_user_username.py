"""Add username to users for KYC signup wizard.

Revision ID: 003_add_user_username
Revises: 002_add_solicitud_radio
Create Date: 2026-09-07
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '003_add_user_username'
down_revision = '002_add_solicitud_radio'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('username', sa.String(length=60), nullable=True))
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)


def downgrade():
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_column('users', 'username')
