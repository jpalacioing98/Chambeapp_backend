"""portafolio: galería antes/después y fotos normales

Revision ID: 022_portfolio_galeria
Revises: 021_preferencia_mapa
Create Date: 2026-11-11 00:00:00.000000

Permite guardar en cada item del portafolio:
- antes:   URLs de fotos del ANTES.
- despues: URLs de fotos del DESPUÉS.
- galeria: URLs de fotos normales (sin comparación).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "022_portfolio_galeria"
down_revision: Union[str, None] = "021_preferencia_mapa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for columna in ("antes", "despues", "galeria"):
        op.add_column(
            "portfolio_items",
            sa.Column(
                columna,
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'::json"),
            ),
        )


def downgrade() -> None:
    for columna in ("galeria", "despues", "antes"):
        op.drop_column("portfolio_items", columna)
