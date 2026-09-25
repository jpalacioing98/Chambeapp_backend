"""habilidades + habilidad_niveles (rutas certificables)

Revision ID: f2a1c4e8d9b0
Revises: ac89426b23a3
Create Date: 2026-09-20 01:10:00.000000

Manual (sin autogenerar): solo las dos tablas nuevas del módulo de
habilidades con rutas de niveles certificables (quiz / certificación).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f2a1c4e8d9b0'
down_revision: Union[str, None] = 'ac89426b23a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'habilidades',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(length=120), nullable=False),
        sa.Column('descripcion', sa.String(length=500), nullable=True),
        sa.Column('niveles', sa.JSON(), nullable=False),
        sa.Column('activa', sa.Boolean(), nullable=False),
        sa.Column('creado_en', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_habilidades_nombre'), 'habilidades', ['nombre'], unique=True
    )

    op.create_table(
        'habilidad_niveles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('habilidad_id', sa.Integer(), nullable=False),
        sa.Column('nivel_index', sa.Integer(), nullable=False),
        sa.Column('metodo', sa.String(length=20), nullable=False),
        sa.Column('evidencia_url', sa.String(length=500), nullable=True),
        sa.Column('fecha', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['habilidad_id'], ['habilidades.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'user_id', 'habilidad_id', 'nivel_index', name='uq_hab_nivel_user'
        ),
    )
    op.create_index(
        op.f('ix_habilidad_niveles_habilidad_id'),
        'habilidad_niveles',
        ['habilidad_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_habilidad_niveles_user_id'),
        'habilidad_niveles',
        ['user_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_habilidad_niveles_user_id'), table_name='habilidad_niveles')
    op.drop_index(op.f('ix_habilidad_niveles_habilidad_id'), table_name='habilidad_niveles')
    op.drop_table('habilidad_niveles')
    op.drop_index(op.f('ix_habilidades_nombre'), table_name='habilidades')
    op.drop_table('habilidades')