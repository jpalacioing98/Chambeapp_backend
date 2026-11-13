"""anuncios: tipo (empleo/servicio/producto) y visibilidad en el mapa

Revision ID: 027_anuncios_tipo_visibilidad
Revises: 026_two_factor_metodos
Create Date: 2026-11-12 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "027_anuncios_tipo_visibilidad"
down_revision: Union[str, None] = "026_two_factor_metodos"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "anuncios_laborales",
        sa.Column(
            "tipo",
            sa.String(length=12),
            nullable=False,
            server_default="empleo",
        ),
    )
    op.add_column(
        "anuncios_laborales",
        sa.Column(
            "visible_mapa",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("anuncios_laborales", "visible_mapa")
    op.drop_column("anuncios_laborales", "tipo")
