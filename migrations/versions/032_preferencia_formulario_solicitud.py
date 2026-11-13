"""preferencia de formulario de solicitud (paso_a_paso | completo)

Revision ID: 032_formulario_solicitud
Revises: 031_cobros_monedas
Create Date: 2026-11-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "032_formulario_solicitud"
down_revision: Union[str, None] = "031_cobros_monedas"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "merchant_preferences",
        sa.Column(
            "formulario_solicitud",
            sa.String(length=12),
            nullable=False,
            server_default="paso_a_paso",
        ),
    )


def downgrade() -> None:
    op.drop_column("merchant_preferences", "formulario_solicitud")
