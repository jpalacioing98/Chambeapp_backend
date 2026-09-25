"""Add Chamba module: tabla chambas (expediente de ejecución de contratos).

Revision ID: 009_add_chamba_module
Revises: e5b8c1d4f6a9
Create Date: 2026-09-22

Manual (sin autogenerar): solo la tabla nueva del módulo de gestión de
chambas, siguiendo el patrón de 004_add_negocios_module (enum vía raw SQL
idempotente + create_type=False).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM

# revision identifiers, used by Alembic.
revision: str = '009_add_chamba_module'
down_revision: Union[str, None] = 'e5b8c1d4f6a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Enum (CREATE TYPE IF NOT EXISTS via raw SQL) ───────────────────
    op.execute(
        "DO $$ BEGIN CREATE TYPE estadochamba AS ENUM ("
        "'programada','en_proceso','en_ejecucion','pausada',"
        "'pendiente_validacion','liquidacion_confirmada','finalizada');"
        " EXCEPTION WHEN duplicate_object THEN null; END $$"
    )
    # create_type=False: el tipo ya lo creó el bloque DO (sa.Enum genérico
    # NO soporta create_type y reintentaría CREATE TYPE → DuplicateObject).
    estado_chamba = ENUM(
        'programada', 'en_proceso', 'en_ejecucion', 'pausada',
        'pendiente_validacion', 'liquidacion_confirmada', 'finalizada',
        name='estadochamba', create_type=False,
    )

    # ── Tabla chambas ──────────────────────────────────────────────────
    op.create_table(
        'chambas',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('contract_id', sa.Integer(),
                  sa.ForeignKey('contracts.id', ondelete='CASCADE'),
                  nullable=False, unique=True),
        sa.Column('estado', estado_chamba, nullable=False,
                  server_default='programada'),
        sa.Column('estado_previo', estado_chamba, nullable=True),
        sa.Column('fecha_activacion', sa.DateTime(), nullable=True),
        sa.Column('fecha_inicio_obra', sa.DateTime(), nullable=True),
        sa.Column('fecha_solicitud_cierre', sa.DateTime(), nullable=True),
        sa.Column('fecha_liquidacion', sa.DateTime(), nullable=True),
        sa.Column('fecha_finalizacion', sa.DateTime(), nullable=True),
        sa.Column('evidencia_entrada', sa.JSON(), nullable=False,
                  server_default='[]'),
        sa.Column('evidencia_salida', sa.JSON(), nullable=False,
                  server_default='[]'),
        sa.Column('adendas', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('novedades', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('pago_confirmado_solicitante', sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column('pago_confirmado_prestador', sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column('pago_directo_confirmado', sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column('pago_monto_final', sa.Integer(), nullable=True),
        sa.Column('rating_estrellas', sa.Integer(), nullable=True),
        sa.Column('rating_comentario', sa.Text(), nullable=True),
        sa.Column('habilidades_validadas', sa.JSON(), nullable=True),
        sa.Column('creado_en', sa.DateTime(), nullable=True),
        sa.Column('actualizado_en', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_chambas_contract_id', 'chambas', ['contract_id'],
                    unique=True)
    op.create_index('ix_chambas_estado', 'chambas', ['estado'])


def downgrade() -> None:
    op.drop_index('ix_chambas_estado', table_name='chambas')
    op.drop_index('ix_chambas_contract_id', table_name='chambas')
    op.drop_table('chambas')
    op.execute("DROP TYPE IF EXISTS estadochamba")