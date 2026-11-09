"""Índices compuestos para feeds, listados y conteos (performance).

Cada índice corresponde a un filtro + orden usado por los endpoints:

- solicitudes: feed público (estado, creado_en), filtro por categoría y
  "mis solicitudes".
- contracts: "mis contratos" por solicitante o proveedor.
- ofertas: ofertas por solicitud y "mis ofertas".
- notifications: bandeja por usuario y conteo de no leídas.
- conversations/messages: lista de chats e historial por conversación.
- negocios: listado/mapa por estado y categoría.
- anuncios: feed público y anuncios de un negocio.
- maranas: feed y listados por solicitante/prestador.
- recommendation_logs: feedback de recomendaciones por solicitud/PDS.
- admin: disputes, tickets, verifications y documentos pendientes.

Revision ID: 017_performance_indexes
Revises: 016_notification_cascades
Create Date: 2026-11-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "017_performance_indexes"
down_revision: Union[str, None] = "016_notification_cascades"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_INDEXES = (
    ("solicitudes", "ix_solicitudes_estado_creado", ("estado", "creado_en")),
    (
        "solicitudes",
        "ix_solicitudes_estado_categoria_creado",
        ("estado", "categoria", "creado_en"),
    ),
    (
        "solicitudes",
        "ix_solicitudes_solicitante_creado",
        ("solicitante_id", "creado_en"),
    ),
    (
        "contracts",
        "ix_contracts_proveedor_creado",
        ("proveedor_id", "creado_en"),
    ),
    (
        "contracts",
        "ix_contracts_solicitante_creado",
        ("solicitante_id", "creado_en"),
    ),
    (
        "contracts",
        "ix_contracts_estado_creado",
        ("estado", "creado_en"),
    ),
    (
        "ofertas",
        "ix_ofertas_solicitud_creado",
        ("solicitud_id", "created_at"),
    ),
    ("ofertas", "ix_ofertas_pds_creado", ("pds_id", "created_at")),
    (
        "notifications",
        "ix_notifications_user_creado",
        ("user_id", "creado_en"),
    ),
    (
        "notifications",
        "ix_notifications_user_leida_creado",
        ("user_id", "leida", "creado_en"),
    ),
    (
        "messages",
        "ix_messages_conversation_creado",
        ("conversation_id", "creado_en"),
    ),
    (
        "conversations",
        "ix_conversations_user_a_creado",
        ("user_a_id", "creado_en"),
    ),
    (
        "conversations",
        "ix_conversations_user_b_creado",
        ("user_b_id", "creado_en"),
    ),
    (
        "negocios",
        "ix_negocios_estado_calificacion",
        ("estado", "calificacion_promedio"),
    ),
    (
        "negocios",
        "ix_negocios_estado_categoria",
        ("estado", "categoria_principal"),
    ),
    (
        "anuncios_laborales",
        "ix_anuncios_estado_creado",
        ("estado", "creado_en"),
    ),
    (
        "anuncios_laborales",
        "ix_anuncios_negocio_creado",
        ("negocio_id", "creado_en"),
    ),
    ("maranas", "ix_maranas_estado_creado", ("estado", "creado_en")),
    (
        "maranas",
        "ix_maranas_solicitante_creado",
        ("solicitante_id", "creado_en"),
    ),
    ("maranas", "ix_maranas_pds_creado", ("pds_asignado_id", "creado_en")),
    (
        "recommendation_logs",
        "ix_recommendation_logs_solicitud_pds",
        ("solicitud_id", "pds_id"),
    ),
    (
        "disputes",
        "ix_disputes_contract_creado",
        ("contract_id", "created_at"),
    ),
    ("disputes", "ix_disputes_status_creado", ("status", "created_at")),
    ("tickets", "ix_tickets_user_creado", ("user_id", "created_at")),
    ("tickets", "ix_tickets_status_creado", ("status", "created_at")),
    (
        "verifications",
        "ix_verifications_status_creado",
        ("status", "created_at"),
    ),
    (
        "documentos_usuario",
        "ix_documentos_usuario_estado_user",
        ("estado", "user_id"),
    ),
)

_OLD_INDEXES = (
    ("solicitudes", "ix_solicitudes_solicitante_id", ("solicitante_id",)),
    ("contracts", "ix_contracts_proveedor_id", ("proveedor_id",)),
    ("contracts", "ix_contracts_solicitante_id", ("solicitante_id",)),
    ("ofertas", "ix_ofertas_solicitud_id", ("solicitud_id",)),
    ("ofertas", "ix_ofertas_pds_id", ("pds_id",)),
    ("notifications", "ix_notifications_user_id", ("user_id",)),
    ("messages", "ix_messages_conversation_id", ("conversation_id",)),
    ("conversations", "ix_conversations_user_a_id", ("user_a_id",)),
    ("conversations", "ix_conversations_user_b_id", ("user_b_id",)),
    ("anuncios_laborales", "ix_anuncios_laborales_negocio_id", ("negocio_id",)),
    ("maranas", "ix_maranas_solicitante_id", ("solicitante_id",)),
    ("maranas", "ix_maranas_pds_asignado_id", ("pds_asignado_id",)),
    ("disputes", "ix_disputes_contract_id", ("contract_id",)),
    ("disputes", "ix_disputes_status", ("status",)),
    ("tickets", "ix_tickets_user_id", ("user_id",)),
    ("tickets", "ix_tickets_status", ("status",)),
    ("verifications", "ix_verifications_status", ("status",)),
)


def _index_names(inspector, table: str) -> set:
    if table not in inspector.get_table_names():
        return set()
    return {item["name"] for item in inspector.get_indexes(table)}


def _create_indexes(indexes, inspector) -> None:
    for table, name, columns in indexes:
        if name not in _index_names(inspector, table):
            op.create_index(name, table, list(columns))


def _drop_indexes(indexes, inspector) -> None:
    for table, name, _columns in indexes:
        if name in _index_names(inspector, table):
            op.drop_index(name, table_name=table)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    _drop_indexes(_OLD_INDEXES, inspector)
    _create_indexes(_NEW_INDEXES, inspector)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    _drop_indexes(_NEW_INDEXES, inspector)
    _create_indexes(_OLD_INDEXES, inspector)
