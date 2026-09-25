"""Add Anuncios Laborales: ofertas laborales no vinculantes de negocios.

Tablas: anuncios_laborales + anuncios_postulaciones (gestión de contacto).
Enums estadoanuncio / estadopostulacion (raw DO idempotente, patrón 011).

Revision ID: 013_anuncios
Revises: 012_fecha_validacion
Create Date: 2026-09-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM

# revision identifiers, used by Alembic.
revision: str = '013_anuncios'
down_revision: Union[str, None] = '012_fecha_validacion'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Enums (idempotentes) ───────────────────────────────────────────
    op.execute(
        "DO $$ BEGIN CREATE TYPE estadoanuncio AS ENUM ("
        "'publicado','cerrado');"
        " EXCEPTION WHEN duplicate_object THEN null; END $$"
    )
    estado_anuncio = ENUM(
        'publicado', 'cerrado', name='estadoanuncio', create_type=False,
    )
    op.execute(
        "DO $$ BEGIN CREATE TYPE estadopostulacion AS ENUM ("
        "'pendiente','contactado','descartado');"
        " EXCEPTION WHEN duplicate_object THEN null; END $$"
    )
    estado_postulacion = ENUM(
        'pendiente', 'contactado', 'descartado',
        name='estadopostulacion', create_type=False,
    )

    # ── Tabla anuncios_laborales ───────────────────────────────────────
    op.create_table(
        'anuncios_laborales',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('negocio_id', sa.Integer(),
                  sa.ForeignKey('users.id'), nullable=False),
        sa.Column('titulo', sa.String(200), nullable=False),
        sa.Column('descripcion', sa.Text(), nullable=False),
        sa.Column('categoria', sa.String(120), nullable=False),
        sa.Column('ubicacion', sa.String(160), nullable=True),
        sa.Column('latitud', sa.Float(), nullable=True),
        sa.Column('longitud', sa.Float(), nullable=True),
        sa.Column('vacantes', sa.Integer(), nullable=True),
        sa.Column('estado', estado_anuncio, nullable=False,
                  server_default='publicado'),
        sa.Column('creado_en', sa.DateTime(), nullable=True),
        sa.Column('actualizado_en', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_anuncios_laborales_negocio_id', 'anuncios_laborales', ['negocio_id'])

    # ── Tabla anuncios_postulaciones ───────────────────────────────────
    op.create_table(
        'anuncios_postulaciones',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('anuncio_id', sa.Integer(),
                  sa.ForeignKey('anuncios_laborales.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('pds_id', sa.Integer(),
                  sa.ForeignKey('users.id'), nullable=False),
        sa.Column('mensaje', sa.Text(), nullable=True),
        sa.Column('telefono_contacto', sa.String(40), nullable=True),
        sa.Column('email_contacto', sa.String(120), nullable=True),
        sa.Column('estado', estado_postulacion, nullable=False,
                  server_default='pendiente'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_anuncios_postulaciones_anuncio_id', 'anuncios_postulaciones', ['anuncio_id'])
    op.create_index('ix_anuncios_postulaciones_pds_id', 'anuncios_postulaciones', ['pds_id'])


def downgrade() -> None:
    op.drop_index('ix_anuncios_postulaciones_pds_id', table_name='anuncios_postulaciones')
    op.drop_index('ix_anuncios_postulaciones_anuncio_id', table_name='anuncios_postulaciones')
    op.drop_table('anuncios_postulaciones')
    op.drop_index('ix_anuncios_laborales_negocio_id', table_name='anuncios_laborales')
    op.drop_table('anuncios_laborales')
    op.execute("DROP TYPE IF EXISTS estadopostulacion")
    op.execute("DROP TYPE IF EXISTS estadoanuncio")