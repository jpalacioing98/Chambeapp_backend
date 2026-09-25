"""Add Chamba: fecha_validacion (revisión y validación del solicitante).

Revision ID: 012_fecha_validacion
Revises: 011_marana_module
Create Date: 2026-09-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '012_fecha_validacion'
down_revision: Union[str, None] = '011_marana_module'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('chambas', sa.Column('fecha_validacion', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('chambas', 'fecha_validacion')