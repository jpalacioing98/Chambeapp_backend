"""cobros en monedas: tarifas configurables y cobro de firmas

Revision ID: 031_cobros_monedas
Revises: 030_ticket_categoria
Create Date: 2026-11-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "031_cobros_monedas"
down_revision: Union[str, None] = "030_ticket_categoria"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tarifas_cobro",
        sa.Column("clave", sa.String(length=50), primary_key=True),
        sa.Column("valor", sa.Float(), nullable=False),
        sa.Column("descripcion", sa.String(length=255), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(), nullable=False),
        sa.Column(
            "actualizado_por",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )

    for columna in (
        "cobro_solicitante_monedas",
        "cobro_proveedor_monedas",
    ):
        op.add_column("contracts", sa.Column(columna, sa.Integer(), nullable=True))

    for columna in (
        "cobro_solicitante_ref",
        "cobro_proveedor_ref",
    ):
        op.add_column(
            "contracts", sa.Column(columna, sa.String(length=100), nullable=True)
        )

    for columna in (
        "cobro_solicitante_en",
        "cobro_proveedor_en",
    ):
        op.add_column("contracts", sa.Column(columna, sa.DateTime(), nullable=True))

    op.add_column(
        "contracts",
        sa.Column(
            "cobros_reembolsados",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("contracts", "cobros_reembolsados")
    for columna in (
        "cobro_solicitante_en",
        "cobro_proveedor_en",
        "cobro_solicitante_ref",
        "cobro_proveedor_ref",
        "cobro_solicitante_monedas",
        "cobro_proveedor_monedas",
    ):
        op.drop_column("contracts", columna)
    op.drop_table("tarifas_cobro")
