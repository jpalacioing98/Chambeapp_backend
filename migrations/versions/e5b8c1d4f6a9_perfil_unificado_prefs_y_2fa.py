"""perfil unificado: preferencias para todos los roles + 2FA

Revision ID: e5b8c1d4f6a9
Revises: d7e9f1b3c5a7
Create Date: 2026-09-22 08:00:00.000000

Añade al perfil unificado (PDS, Solicitante, Comerciante):
- users.two_factor_enabled: autenticación en dos pasos (toggle persistido).
- merchant_preferences.idioma / tema: preferencias UI disponibles para
  todos los roles (el modelo se reutiliza como "preferencias de usuario").
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e5b8c1d4f6a9'
down_revision: Union[str, None] = 'd7e9f1b3c5a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('two_factor_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        'merchant_preferences',
        sa.Column('idioma', sa.String(length=5), nullable=False, server_default='es'),
    )
    op.add_column(
        'merchant_preferences',
        sa.Column('tema', sa.String(length=10), nullable=False, server_default='system'),
    )


def downgrade() -> None:
    op.drop_column('merchant_preferences', 'tema')
    op.drop_column('merchant_preferences', 'idioma')
    op.drop_column('users', 'two_factor_enabled')