"""Add Oferta: parámetros "a convenir" (fecha deseada y franja horaria).

El PDS concreta desde su oferta los parámetros que la solicitud dejó "a
convenir" (presupuesto, fecha_deseada, horario), y la contraoferta del
chat permite ajustarlos (contra_fecha_deseada/contra_horario).

Revision ID: 010_add_oferta_parametros_convenir
Revises: 009_add_chamba_module
Create Date: 2026-09-22
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '010_convenir_parametros'
down_revision: Union[str, None] = '009_add_chamba_module'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('ofertas', sa.Column('fecha_deseada', sa.Date(), nullable=True))
    op.add_column('ofertas', sa.Column('horario', sa.String(length=80), nullable=True))
    op.add_column('ofertas', sa.Column('contra_fecha_deseada', sa.Date(), nullable=True))
    op.add_column('ofertas', sa.Column('contra_horario', sa.String(length=80), nullable=True))


def downgrade() -> None:
    op.drop_column('ofertas', 'contra_horario')
    op.drop_column('ofertas', 'contra_fecha_deseada')
    op.drop_column('ofertas', 'horario')
    op.drop_column('ofertas', 'fecha_deseada')