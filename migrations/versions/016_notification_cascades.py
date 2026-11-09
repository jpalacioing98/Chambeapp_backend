"""Create notification_cascades (notificaciones en cascada por fases).

Tabla `notification_cascades`: una fila por solicitud que tenga una cascada
de notificaciones activa. Guarda la fase actual, la configuración de fases
(radio/delay/candidatos por fase), el estado y el log de actividad.

El modelo (`app/models/cascade.py`) estaba registrado sólo cuando alguien lo
importaba desde su submódulo, así que `db.create_all()` no siempre creaba la
tabla y el seed de simulación fallaba con
`relation "notification_cascades" does not exist`.

Revision ID: 016_notification_cascades
Revises: 015_recommendation_logs
Create Date: 2026-10-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '016_notification_cascades'
down_revision: Union[str, None] = '015_recommendation_logs'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ESTADOS = ('activa', 'completada', 'expirada', 'cancelada')


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "notification_cascades" in inspector.get_table_names():
        return

    op.create_table(
        'notification_cascades',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('solicitud_id', sa.Integer(), nullable=True),
        sa.Column('fase_actual', sa.Integer(), nullable=True),
        sa.Column('config_json', sa.JSON(), nullable=True),
        sa.Column(
            'estado',
            sa.Enum(*_ESTADOS, name='cascade_estado'),
            nullable=True,
        ),
        sa.Column('enviados_total', sa.Integer(), nullable=True),
        sa.Column('respondidos_total', sa.Integer(), nullable=True),
        sa.Column('timer_expira', sa.DateTime(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('log_json', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['solicitud_id'], ['solicitudes.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('solicitud_id'),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "notification_cascades" not in inspector.get_table_names():
        return

    op.drop_table('notification_cascades')
