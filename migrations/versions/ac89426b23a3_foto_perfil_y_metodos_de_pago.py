"""foto_perfil en profiles + tabla metodos_pago

Revision ID: ac89426b23a3
Revises: 008_drop_payment_retention
Create Date: 2026-09-19 22:52:08.410642

Contenido manual (NO autogenerado): la autogeneración incluía drops de
tablas de la extensión postgis_tiger_geocoder. Solo se migra lo que el
código necesita:
· profiles.foto_perfil            (foto de perfil, RF-02)
· metodos_pago                    (métodos de pago vinculados, RF-08)
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'ac89426b23a3'
down_revision: Union[str, None] = '008_drop_payment_retention'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'profiles',
        sa.Column('foto_perfil', sa.String(length=500), nullable=True),
    )

    op.create_table(
        'metodos_pago',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('tipo', sa.String(length=30), nullable=False),
        sa.Column('banco', sa.String(length=120), nullable=True),
        sa.Column('numero_cuenta', sa.String(length=60), nullable=True),
        sa.Column('es_principal', sa.Boolean(), nullable=False),
        sa.Column('creado_en', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_metodos_pago_user_id'), 'metodos_pago', ['user_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_metodos_pago_user_id'), table_name='metodos_pago')
    op.drop_table('metodos_pago')
    op.drop_column('profiles', 'foto_perfil')