"""preferencia de mapa (2d/3d) en el perfil unificado

Revision ID: 021_preferencia_mapa
Revises: 020_cascade_notificaciones
Create Date: 2026-11-11 00:00:00.000000

Añade `merchant_preferences.mapa_preferido` para que la vista de chambas
del PDS arranque en 2D o 3D según la preferencia del usuario.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "021_preferencia_mapa"
down_revision: Union[str, None] = "020_cascade_notificaciones"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "merchant_preferences",
        sa.Column(
            "mapa_preferido",
            sa.String(length=4),
            nullable=False,
            server_default="2d",
        ),
    )


def downgrade() -> None:
    op.drop_column("merchant_preferences", "mapa_preferido")
