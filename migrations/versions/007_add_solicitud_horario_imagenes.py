"""Add horario + imagenes to solicitudes (publicar chamba enriquecido).

· horario  → franja horaria preferida declarada por el solicitante.
· imagenes → hasta 3 fotos adjuntas (data URL base64, mismo patrón que KYC).

Revision ID: 007_add_solicitud_horario_imagenes
Revises: 006_create_trust_scores
Create Date: 2026-09-17
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '007_add_solicitud_horario_imagenes'
down_revision = '006_create_trust_scores'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('solicitudes', sa.Column('horario', sa.String(80), nullable=True))
    op.add_column('solicitudes', sa.Column('imagenes', sa.JSON(), nullable=True))
    # El barrido 360 guarda una equirectangular en data URL (cientos de KB):
    # con VARCHAR(500) Postgres la rechazaba.
    op.alter_column('solicitudes', 'imagen_360', type_=sa.Text(), existing_nullable=True)


def downgrade():
    op.alter_column('solicitudes', 'imagen_360', type_=sa.String(500), existing_nullable=True)
    op.drop_column('solicitudes', 'imagenes')
    op.drop_column('solicitudes', 'horario')
