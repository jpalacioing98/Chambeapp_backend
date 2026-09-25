"""competencias en habilidades + endoso_habilidades + certificaciones_tecnicas

Revision ID: c3d5e7f9a1b2
Revises: f2a1c4e8d9b0
Create Date: 2026-09-20 02:30:00.000000

Módulo de oficios y habilidades (doc): competencias por oficio, endoso
por clientes y formación técnica certificada (SENA/instituciones).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c3d5e7f9a1b2'
down_revision: Union[str, None] = 'f2a1c4e8d9b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'habilidades',
        sa.Column('habilidades', sa.JSON(), nullable=False, server_default='[]'),
    )

    op.create_table(
        'endoso_habilidades',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('contract_id', sa.Integer(), nullable=False),
        sa.Column('pds_id', sa.Integer(), nullable=False),
        sa.Column('solicitante_id', sa.Integer(), nullable=False),
        sa.Column('habilidad_id', sa.Integer(), nullable=False),
        sa.Column('competencia', sa.String(length=150), nullable=False),
        sa.Column('creado_en', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['contract_id'], ['contracts.id']),
        sa.ForeignKeyConstraint(['habilidad_id'], ['habilidades.id']),
        sa.ForeignKeyConstraint(['pds_id'], ['users.id']),
        sa.ForeignKeyConstraint(['solicitante_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'contract_id', 'pds_id', 'habilidad_id', 'competencia',
            name='uq_endoso_contract_competencia',
        ),
    )
    op.create_index(
        op.f('ix_endoso_habilidades_contract_id'),
        'endoso_habilidades', ['contract_id'], unique=False,
    )
    op.create_index(
        op.f('ix_endoso_habilidades_habilidad_id'),
        'endoso_habilidades', ['habilidad_id'], unique=False,
    )
    op.create_index(
        op.f('ix_endoso_habilidades_pds_id'),
        'endoso_habilidades', ['pds_id'], unique=False,
    )
    op.create_index(
        op.f('ix_endoso_habilidades_solicitante_id'),
        'endoso_habilidades', ['solicitante_id'], unique=False,
    )

    op.create_table(
        'certificaciones_tecnicas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('habilidad_id', sa.Integer(), nullable=True),
        sa.Column('institucion', sa.String(length=150), nullable=False),
        sa.Column('titulo', sa.String(length=200), nullable=False),
        sa.Column('anio', sa.Integer(), nullable=True),
        sa.Column('codigo_verificacion', sa.String(length=120), nullable=True),
        sa.Column('documento_url', sa.String(length=500), nullable=True),
        sa.Column('estado', sa.String(length=20), nullable=False),
        sa.Column('creado_en', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['habilidad_id'], ['habilidades.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_certificaciones_tecnicas_habilidad_id'),
        'certificaciones_tecnicas', ['habilidad_id'], unique=False,
    )
    op.create_index(
        op.f('ix_certificaciones_tecnicas_user_id'),
        'certificaciones_tecnicas', ['user_id'], unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_certificaciones_tecnicas_user_id'),
        table_name='certificaciones_tecnicas',
    )
    op.drop_index(
        op.f('ix_certificaciones_tecnicas_habilidad_id'),
        table_name='certificaciones_tecnicas',
    )
    op.drop_table('certificaciones_tecnicas')
    op.drop_index(
        op.f('ix_endoso_habilidades_solicitante_id'),
        table_name='endoso_habilidades',
    )
    op.drop_index(op.f('ix_endoso_habilidades_pds_id'), table_name='endoso_habilidades')
    op.drop_index(
        op.f('ix_endoso_habilidades_habilidad_id'), table_name='endoso_habilidades'
    )
    op.drop_index(
        op.f('ix_endoso_habilidades_contract_id'), table_name='endoso_habilidades'
    )
    op.drop_table('endoso_habilidades')
    op.drop_column('habilidades', 'habilidades')