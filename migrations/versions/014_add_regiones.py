"""Add Region model + users.region_id (división administrativa regional).

Tabla `regions`: catálogo de regiones de Colombia (Caribe, Andina, Pacífica,
Orinoquía, Amazónica). Columna `users.region_id`: pertenencia de cada usuario
a una región (el personal admin/verificador/soporte la usa para acotar su
operación; el superadmin la deja en NULL = global).

Revision ID: 014_regiones
Revises: 013_anuncios
Create Date: 2026-09-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '014_regiones'
down_revision: Union[str, None] = '013_anuncios'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_REGIONES = [
    {
        "clave": "caribe",
        "nombre": "Región Caribe",
        "descripcion": "Atlántico, Bolívar, Cesar, Córdoba, La Guajira, Magdalena, Sucre, San Andrés.",
        "departamentos": ["Atlántico", "Bolívar", "Cesar", "Córdoba", "La Guajira", "Magdalena", "Sucre", "San Andrés y Providencia"],
    },
    {
        "clave": "andina",
        "nombre": "Región Andina",
        "descripcion": "Antioquia, Boyacá, Caldas, Cundinamarca, Huila, Norte de Santander, Quindío, Risaralda, Santander, Tolima.",
        "departamentos": ["Antioquia", "Boyacá", "Caldas", "Cundinamarca", "Huila", "Norte de Santander", "Quindío", "Risaralda", "Santander", "Tolima"],
    },
    {
        "clave": "pacifica",
        "nombre": "Región Pacífica",
        "descripcion": "Cauca, Chocó, Nariño, Valle del Cauca.",
        "departamentos": ["Cauca", "Chocó", "Nariño", "Valle del Cauca"],
    },
    {
        "clave": "orinoquia",
        "nombre": "Región Orinoquía",
        "descripcion": "Arauca, Casanare, Guainía (parcial), Meta, Vichada.",
        "departamentos": ["Arauca", "Casanare", "Meta", "Vichada"],
    },
    {
        "clave": "amazonia",
        "nombre": "Región Amazónica",
        "descripcion": "Amazonas, Caquetá, Guainía, Guaviare, Putumayo, Vaupés.",
        "departamentos": ["Amazonas", "Caquetá", "Guainía", "Guaviare", "Putumayo", "Vaupés"],
    },
]


def upgrade() -> None:
    op.create_table(
        'regions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('clave', sa.String(40), nullable=False, unique=True),
        sa.Column('nombre', sa.String(120), nullable=False),
        sa.Column('descripcion', sa.Text(), nullable=True),
        sa.Column('departamentos', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_regions_clave', 'regions', ['clave'])

    region_table = sa.table(
        'regions',
        sa.column('clave', sa.String),
        sa.column('nombre', sa.String),
        sa.column('descripcion', sa.Text),
        sa.column('departamentos', sa.JSON),
    )
    op.bulk_insert(region_table, _REGIONES)

    op.add_column(
        'users',
        sa.Column('region_id', sa.Integer(), sa.ForeignKey('regions.id'), nullable=True),
    )
    op.create_index('ix_users_region_id', 'users', ['region_id'])


def downgrade() -> None:
    op.drop_index('ix_users_region_id', table_name='users')
    op.drop_column('users', 'region_id')
    op.drop_index('ix_regions_clave', table_name='regions')
    op.drop_table('regions')