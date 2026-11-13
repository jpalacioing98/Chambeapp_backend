"""tickets: categoría/tipo de ticket

Revision ID: 030_ticket_categoria
Revises: 029_negocio_rutas
Create Date: 2026-11-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "030_ticket_categoria"
down_revision: Union[str, None] = "029_negocio_rutas"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tickets",
        sa.Column(
            "category",
            sa.String(length=40),
            nullable=False,
            server_default="otro",
        ),
    )


def downgrade() -> None:
    op.drop_column("tickets", "category")
