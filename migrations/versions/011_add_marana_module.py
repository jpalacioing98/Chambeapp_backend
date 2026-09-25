"""Add Maraña (rebusque) module: orden menor derivada de una adenda.

Tablas: maranas + maranas_ofertas (negociación tipo ofertas de chambas)
y enums estadoMarana / estadoMaranaOferta (raw DO idempotente, igual que
009/004).

Revision ID: 011_marana_module
Revises: 010_convenir_parametros
Create Date: 2026-09-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM

# revision identifiers, used by Alembic.
revision: str = '011_marana_module'
down_revision: Union[str, None] = '010_convenir_parametros'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Enums (idempotentes) ───────────────────────────────────────────
    op.execute(
        "DO $$ BEGIN CREATE TYPE estadomarana AS ENUM ("
        "'publicado','asignado','completado','pagado','cancelado');"
        " EXCEPTION WHEN duplicate_object THEN null; END $$"
    )
    estado_marana = ENUM(
        'publicado', 'asignado', 'completado', 'pagado', 'cancelado',
        name='estadomarana', create_type=False,
    )
    op.execute(
        "DO $$ BEGIN CREATE TYPE estadomaranaoferta AS ENUM ("
        "'pendiente','aceptada','rechazada','contraoferta');"
        " EXCEPTION WHEN duplicate_object THEN null; END $$"
    )
    estado_marana_oferta = ENUM(
        'pendiente', 'aceptada', 'rechazada', 'contraoferta',
        name='estadomaranaoferta', create_type=False,
    )

    # ── Tabla maranas ──────────────────────────────────────────────────
    op.create_table(
        'maranas',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('chamba_id', sa.Integer(),
                  sa.ForeignKey('chambas.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('adenda_idx', sa.Integer(), nullable=True),
        sa.Column('solicitante_id', sa.Integer(),
                  sa.ForeignKey('users.id'), nullable=False),
        sa.Column('titulo', sa.String(200), nullable=False),
        sa.Column('categoria', sa.String(120), nullable=False),
        sa.Column('descripcion', sa.Text(), nullable=False),
        sa.Column('presupuesto', sa.Integer(), nullable=True),
        sa.Column('ubicacion', sa.String(120), nullable=True),
        sa.Column('fecha_deseada', sa.Date(), nullable=True),
        sa.Column('horario', sa.String(80), nullable=True),
        sa.Column('estado', estado_marana, nullable=False,
                  server_default='publicado'),
        sa.Column('pago_confirmado_solicitante', sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column('pago_confirmado_prestador', sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column('pago_monto_final', sa.Integer(), nullable=True),
        sa.Column('pds_asignado_id', sa.Integer(),
                  sa.ForeignKey('users.id'), nullable=True),
        sa.Column('fecha_asignacion', sa.DateTime(), nullable=True),
        sa.Column('fecha_entrega', sa.DateTime(), nullable=True),
        sa.Column('fecha_pago', sa.DateTime(), nullable=True),
        sa.Column('creado_en', sa.DateTime(), nullable=True),
        sa.Column('actualizado_en', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_maranas_chamba_id', 'maranas', ['chamba_id'])
    op.create_index('ix_maranas_solicitante_id', 'maranas', ['solicitante_id'])
    op.create_index('ix_maranas_pds_asignado_id', 'maranas', ['pds_asignado_id'])

    # ── Tabla maranas_ofertas ──────────────────────────────────────────
    op.create_table(
        'maranas_ofertas',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('marana_id', sa.Integer(),
                  sa.ForeignKey('maranas.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('pds_id', sa.Integer(),
                  sa.ForeignKey('users.id'), nullable=False),
        sa.Column('monto', sa.Integer(), nullable=True),
        sa.Column('mensaje', sa.Text(), nullable=True),
        sa.Column('estado', estado_marana_oferta, nullable=False,
                  server_default='pendiente'),
        sa.Column('contra_monto', sa.Integer(), nullable=True),
        sa.Column('contra_mensaje', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_maranas_ofertas_marana_id', 'maranas_ofertas', ['marana_id'])
    op.create_index('ix_maranas_ofertas_pds_id', 'maranas_ofertas', ['pds_id'])


def downgrade() -> None:
    op.drop_index('ix_maranas_ofertas_pds_id', table_name='maranas_ofertas')
    op.drop_index('ix_maranas_ofertas_marana_id', table_name='maranas_ofertas')
    op.drop_table('maranas_ofertas')
    op.drop_index('ix_maranas_pds_asignado_id', table_name='maranas')
    op.drop_index('ix_maranas_solicitante_id', table_name='maranas')
    op.drop_index('ix_maranas_chamba_id', table_name='maranas')
    op.drop_table('maranas')
    op.execute("DROP TYPE IF EXISTS estadomaranaoferta")
    op.execute("DROP TYPE IF EXISTS estadomarana")