"""anuncios: postulantes pds/solicitante, selección y motivo de cierre

Revision ID: 034_anuncios_contacto
Revises: 033_analytics_history
Create Date: 2026-11-18

Los anuncios son de contacto: PDS y solicitantes pueden postularse, el
negocio marca un único perfil seleccionado y, si cierra sin selección,
registra el motivo. No se generan contratos desde anuncios.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "034_anuncios_contacto"
down_revision: Union[str, None] = "033_analytics_history"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "anuncios_laborales",
        sa.Column("motivo_cierre", sa.Text(), nullable=True),
    )
    op.add_column(
        "anuncios_postulaciones",
        sa.Column(
            "postulante_rol",
            sa.String(length=20),
            nullable=False,
            server_default="pds",
        ),
    )
    op.add_column(
        "anuncios_postulaciones",
        sa.Column(
            "seleccionado",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("anuncios_postulaciones", "seleccionado")
    op.drop_column("anuncios_postulaciones", "postulante_rol")
    op.drop_column("anuncios_laborales", "motivo_cierre")
