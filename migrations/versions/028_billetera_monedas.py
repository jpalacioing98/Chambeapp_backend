"""billetera de monedas: paquetes, compras y libro de movimientos

Revision ID: 028_billetera_monedas
Revises: 027_anuncios_tipo_visibilidad
Create Date: 2026-11-12

Reemplaza la lógica de recargas por monedas virtuales compradas en paquetes.
El saldo COP se conserva para los pagos de contratos.
"""

from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "028_billetera_monedas"
down_revision: Union[str, None] = "027_anuncios_tipo_visibilidad"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PAQUETES = [
    {
        "nombre": "Básico",
        "descripcion": "Para empezar a destacar tus publicaciones.",
        "cantidad": 50,
        "bonus": 0,
        "precio_cop": 5000,
        "activo": True,
        "en_oferta": False,
        "orden": 1,
        "creado_en": datetime.now(timezone.utc),
        "actualizado_en": datetime.now(timezone.utc),
    },
    {
        "nombre": "Estándar",
        "descripcion": "El más elegido: monedas extra de regalo.",
        "cantidad": 150,
        "bonus": 15,
        "precio_cop": 15000,
        "activo": True,
        "en_oferta": False,
        "orden": 2,
        "creado_en": datetime.now(timezone.utc),
        "actualizado_en": datetime.now(timezone.utc),
    },
    {
        "nombre": "Premium",
        "descripcion": "Máximo ahorro por moneda para negocios activos.",
        "cantidad": 350,
        "bonus": 50,
        "precio_cop": 30000,
        "activo": True,
        "en_oferta": False,
        "orden": 3,
        "creado_en": datetime.now(timezone.utc),
        "actualizado_en": datetime.now(timezone.utc),
    },
]


def upgrade() -> None:
    op.add_column(
        "wallets",
        sa.Column(
            "monedas_saldo",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    paquetes = op.create_table(
        "paquetes_monedas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nombre", sa.String(length=80), nullable=False),
        sa.Column("descripcion", sa.String(length=255), nullable=True),
        sa.Column("cantidad", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bonus", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("precio_cop", sa.Integer(), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("en_oferta", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("precio_oferta_cop", sa.Integer(), nullable=True),
        sa.Column("oferta_desde", sa.DateTime(), nullable=True),
        sa.Column("oferta_hasta", sa.DateTime(), nullable=True),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("creado_por", sa.Integer(), nullable=True),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["creado_por"], ["users.id"]),
    )

    op.create_table(
        "compras_paquetes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("paquete_id", sa.Integer(), nullable=True),
        sa.Column("monedas", sa.Integer(), nullable=False),
        sa.Column("precio_cop", sa.Integer(), nullable=False),
        sa.Column("pasarela", sa.String(length=40), nullable=False, server_default="simulada"),
        sa.Column("estado", sa.String(length=20), nullable=False, server_default="completado"),
        sa.Column("referencia", sa.String(length=100), nullable=True),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["paquete_id"], ["paquetes_monedas.id"]),
    )
    op.create_index("ix_compras_paquetes_user_id", "compras_paquetes", ["user_id"])
    op.create_index("ix_compras_paquetes_paquete_id", "compras_paquetes", ["paquete_id"])

    op.create_table(
        "movimientos_monedas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("wallet_id", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.Column("saldo_resultante", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("descripcion", sa.String(length=255), nullable=True),
        sa.Column("referencia", sa.String(length=100), nullable=True),
        sa.Column("paquete_id", sa.Integer(), nullable=True),
        sa.Column("vence_en", sa.DateTime(), nullable=True),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["wallet_id"], ["wallets.id"]),
        sa.ForeignKeyConstraint(["paquete_id"], ["paquetes_monedas.id"]),
    )
    op.create_index("ix_movimientos_monedas_user_id", "movimientos_monedas", ["user_id"])
    op.create_index("ix_movimientos_monedas_wallet_id", "movimientos_monedas", ["wallet_id"])
    op.create_index("ix_movimientos_monedas_tipo", "movimientos_monedas", ["tipo"])
    op.create_index(
        "ix_movimientos_monedas_user_creado",
        "movimientos_monedas",
        ["user_id", "creado_en"],
    )

    # Saldo inicial: suma de las monedas existentes por usuario.
    op.execute(
        """
        UPDATE wallets
        SET monedas_saldo = COALESCE((
            SELECT SUM(c.cantidad)
            FROM coins c
            WHERE c.user_id = wallets.user_id
              AND (c.vence_en IS NULL OR c.vence_en > NOW())
        ), 0)
        """
    )

    op.bulk_insert(paquetes, PAQUETES)


def downgrade() -> None:
    op.drop_index("ix_movimientos_monedas_user_creado", table_name="movimientos_monedas")
    op.drop_index("ix_movimientos_monedas_tipo", table_name="movimientos_monedas")
    op.drop_index("ix_movimientos_monedas_wallet_id", table_name="movimientos_monedas")
    op.drop_index("ix_movimientos_monedas_user_id", table_name="movimientos_monedas")
    op.drop_table("movimientos_monedas")
    op.drop_index("ix_compras_paquetes_paquete_id", table_name="compras_paquetes")
    op.drop_index("ix_compras_paquetes_user_id", table_name="compras_paquetes")
    op.drop_table("compras_paquetes")
    op.drop_table("paquetes_monedas")
    op.drop_column("wallets", "monedas_saldo")
