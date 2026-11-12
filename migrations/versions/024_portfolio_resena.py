"""portafolio: reseña del solicitante en el item

Revision ID: 024_portfolio_resena
Revises: 023_portfolio_precio_rating
Create Date: 2026-11-11 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "024_portfolio_resena"
down_revision: Union[str, None] = "023_portfolio_precio_rating"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "portfolio_items",
        sa.Column("resena_texto", sa.Text(), nullable=True),
    )
    op.add_column(
        "portfolio_items",
        sa.Column("resena_autor", sa.String(length=120), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("portfolio_items", "resena_autor")
    op.drop_column("portfolio_items", "resena_texto")
