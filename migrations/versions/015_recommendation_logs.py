"""Create recommendation_logs (feedback A/B del motor de recomendaciones).

Tabla `recommendation_logs`: impresiones del motor, grupo A/B, score,
posición y señales de conversión (notificado/respondio/aceptado) que
alimentan las métricas y el reentrenamiento.

Revision ID: 015_recommendation_logs
Revises: 014_regiones
Create Date: 2026-10-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '015_recommendation_logs'
down_revision: Union[str, None] = '014_regiones'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "recommendation_logs" in inspector.get_table_names():
        return

    op.create_table(
        "recommendation_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("solicitud_id", sa.Integer(), nullable=True),
        sa.Column("pds_id", sa.Integer(), nullable=True),
        sa.Column("puntuacion", sa.Float(), nullable=True),
        sa.Column("ranking_pos", sa.Integer(), nullable=True),
        sa.Column("features_snapshot", sa.JSON(), nullable=True),
        sa.Column("modelo_nombre", sa.String(length=50), nullable=True),
        sa.Column("modelo_version", sa.String(length=50), nullable=True),
        sa.Column("notificado", sa.Boolean(), server_default=sa.false(), nullable=True),
        sa.Column("respondio", sa.Boolean(), server_default=sa.false(), nullable=True),
        sa.Column("aceptado", sa.Boolean(), server_default=sa.false(), nullable=True),
        sa.Column("experiment_group", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["pds_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["solicitud_id"], ["solicitudes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_recommendation_logs_solicitud_id",
        "recommendation_logs",
        ["solicitud_id"],
    )
    op.create_index(
        "ix_recommendation_logs_pds_id",
        "recommendation_logs",
        ["pds_id"],
    )
    op.create_index(
        "ix_recommendation_logs_experiment_group",
        "recommendation_logs",
        ["experiment_group"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "recommendation_logs" not in inspector.get_table_names():
        return

    op.drop_index(
        "ix_recommendation_logs_experiment_group",
        table_name="recommendation_logs",
    )
    op.drop_index(
        "ix_recommendation_logs_pds_id",
        table_name="recommendation_logs",
    )
    op.drop_index(
        "ix_recommendation_logs_solicitud_id",
        table_name="recommendation_logs",
    )
    op.drop_table("recommendation_logs")
