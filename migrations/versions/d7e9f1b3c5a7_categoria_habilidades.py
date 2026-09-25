"""categoria en habilidades (catálogo nacional CUOC/SENA)

Revision ID: d7e9f1b3c5a7
Revises: c3d5e7f9a1b2
Create Date: 2026-09-20 04:00:00.000000

Categoría del catálogo nacional: construccion | climatizacion |
domesticos | estetica | mecanica.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd7e9f1b3c5a7'
down_revision: Union[str, None] = 'c3d5e7f9a1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'habilidades',
        sa.Column('categoria', sa.String(length=60), nullable=True),
    )
    op.create_index(
        op.f('ix_habilidades_categoria'), 'habilidades', ['categoria'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_habilidades_categoria'), table_name='habilidades')
    op.drop_column('habilidades', 'categoria')