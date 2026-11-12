"""Notificaciones en cascada: habilita el flag y ajusta radios/tiempos.

- `feature_flags.cascade_notifications` pasa a `true`: era la bandera maestra
  que apagaba todo el flujo de aviso a PDS (y el código ni siquiera la
  consultaba).
- Las cascadas activas reescriben su `config_json` con los nuevos radios
  (20/50/100 km) y esperas cortas (30 s / 120 s / 300 s).

Revision ID: 020_cascade_notificaciones
Revises: 019_anuncios_vinculantes
Create Date: 2026-11-09
"""

import json

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "020_cascade_notificaciones"
down_revision: str = "019_anuncios_vinculantes"
branch_labels = None
depends_on = None

# Configuración nueva de fases: radio en km, espera tras la fase en segundos
# y tope de candidatos por fase.
NUEVA_CONFIG = [
    {"radius_km": 20.0, "delay_seconds": 30, "max_candidates": 20},
    {"radius_km": 50.0, "delay_seconds": 120, "max_candidates": 40},
    {"radius_km": 100.0, "delay_seconds": 300, "max_candidates": 80},
]

CONFIG_PREVIA = [
    {"radius_km": 2.0, "delay_seconds": 300, "max_candidates": 5},
    {"radius_km": 5.0, "delay_seconds": 600, "max_candidates": 10},
    {"radius_km": 15.0, "delay_seconds": 900, "max_candidates": 15},
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tablas = inspector.get_table_names()

    # 1. Bandera maestra encendida.
    if "feature_flags" in tablas:
        op.execute(
            """
            INSERT INTO feature_flags (key, enabled, description)
            VALUES ('cascade_notifications', true,
                    'Activa notificaciones en cascada y aviso a PDS elegibles')
            ON CONFLICT (key) DO UPDATE SET enabled = true
            """
        )

    # 2. Cascadas activas: nuevos radios y esperas.
    if "notification_cascades" in tablas:
        filas = bind.execute(
            sa.text(
                "SELECT id, config_json FROM notification_cascades "
                "WHERE estado = 'activa'"
            )
        ).fetchall()
        for cascade_id, config_json in filas:
            try:
                config = json.loads(config_json) if isinstance(config_json, str) else config_json
            except (TypeError, ValueError):
                config = None
            if not config:
                config = CONFIG_PREVIA
            op.execute(
                sa.text(
                    "UPDATE notification_cascades SET config_json = :config "
                    "WHERE id = :id"
                ).bindparams(config=json.dumps(NUEVA_CONFIG), id=cascade_id)
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tablas = inspector.get_table_names()

    if "notification_cascades" in tablas:
        filas = bind.execute(
            sa.text(
                "SELECT id FROM notification_cascades WHERE estado = 'activa'"
            )
        ).fetchall()
        for (cascade_id,) in filas:
            op.execute(
                sa.text(
                    "UPDATE notification_cascades SET config_json = :config "
                    "WHERE id = :id"
                ).bindparams(config=json.dumps(CONFIG_PREVIA), id=cascade_id)
            )

    if "feature_flags" in tablas:
        op.execute(
            "UPDATE feature_flags SET enabled = false "
            "WHERE key = 'cascade_notifications'"
        )
