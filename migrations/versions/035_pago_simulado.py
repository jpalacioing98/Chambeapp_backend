"""pagos simulados: checkout realista de paquetes de monedas

Revision ID: 035_pago_simulado
Revises: 034_anuncios_contacto
Create Date: 2026-11-18

Un pago simulado nace en estado `pendiente` sin acreditar monedas. Al
confirmarse (endpoint o webhook simulado) se crea la compra del paquete y
se acreditan las monedas; si expira (15 min) o se cancela queda fallido.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "035_pago_simulado"
down_revision: Union[str, None] = "034_anuncios_contacto"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pagos_simulados",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("paquete_id", sa.Integer(), nullable=True),
        sa.Column("monedas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("precio_cop", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "estado",
            sa.String(length=20),
            nullable=False,
            server_default="pendiente",
        ),
        sa.Column("referencia", sa.String(length=100), nullable=True, unique=True),
        sa.Column(
            "pasarela",
            sa.String(length=40),
            nullable=False,
            server_default="simulada",
        ),
        sa.Column("compra_id", sa.Integer(), nullable=True),
        sa.Column(
            "creado_en",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("expira_en", sa.DateTime(), nullable=True),
        sa.Column("completado_en", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["paquete_id"], ["paquetes_monedas.id"]),
        sa.ForeignKeyConstraint(["compra_id"], ["compras_paquetes.id"]),
    )
    op.create_index(
        "ix_pagos_simulados_user_id", "pagos_simulados", ["user_id"], unique=False
    )
    op.create_index(
        "ix_pagos_simulados_paquete_id",
        "pagos_simulados",
        ["paquete_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_pagos_simulados_paquete_id", table_name="pagos_simulados")
    op.drop_index("ix_pagos_simulados_user_id", table_name="pagos_simulados")
    op.drop_table("pagos_simulados")
