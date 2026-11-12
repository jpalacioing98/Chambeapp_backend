"""portafolio: precio y calificación visibles en la card

Revision ID: 023_portfolio_precio_rating
Revises: 022_portfolio_galeria
Create Date: 2026-11-11 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "023_portfolio_precio_rating"
down_revision: Union[str, None] = "022_portfolio_galeria"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "portfolio_items",
        sa.Column("precio", sa.Integer(), nullable=True),
    )
    op.add_column(
        "portfolio_items",
        sa.Column("calificacion", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("portfolio_items", "calificacion")
    op.drop_column("portfolio_items", "precio")
