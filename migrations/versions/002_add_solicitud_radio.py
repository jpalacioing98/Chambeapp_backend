"""Add radio_km to solicitudes for geofence subsystem.

Revision ID: 002_add_solicitud_radio
Revises: 001_add_postgis_trust
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '002_add_solicitud_radio'
down_revision = '001_add_postgis_trust'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('solicitudes', sa.Column('radio_km', sa.Float(), nullable=True))


def downgrade():
    op.drop_column('solicitudes', 'radio_km')
