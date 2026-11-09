"""Negociación bilateral: aceptación por ambas partes y firma paralela.

- Oferta: flags de aceptación por solicitante y pds, autor de la
  contraoferta, monto final y condiciones acordadas.
- Contract: vínculo con la oferta, monto final, condiciones, parámetros
  "a convenir" y las dos firmas (paralelas) con sus datos y fechas.

Revision ID: 018_negociacion_bilateral
Revises: 017_performance_indexes
Create Date: 2026-11-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "018_negociacion_bilateral"
down_revision: Union[str, None] = "017_performance_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Oferta: aceptación bilateral + valor final + condiciones ---
    op.add_column(
        "ofertas",
        sa.Column("contra_autor", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "ofertas",
        sa.Column(
            "aceptada_por_solicitante",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "ofertas",
        sa.Column(
            "aceptada_por_pds",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column("ofertas", sa.Column("monto_final", sa.Float(), nullable=True))
    op.add_column("ofertas", sa.Column("condiciones", sa.JSON(), nullable=True))
    op.add_column(
        "ofertas", sa.Column("fecha_aceptacion", sa.DateTime(), nullable=True)
    )

    # --- Contract: datos de la negociación + firmas paralelas ---
    op.add_column("contracts", sa.Column("oferta_id", sa.Integer(), nullable=True))
    op.add_column("contracts", sa.Column("monto", sa.Float(), nullable=True))
    op.add_column("contracts", sa.Column("condiciones", sa.JSON(), nullable=True))
    op.add_column("contracts", sa.Column("fecha_deseada", sa.Date(), nullable=True))
    op.add_column(
        "contracts", sa.Column("horario", sa.String(length=80), nullable=True)
    )
    op.add_column(
        "contracts",
        sa.Column(
            "firma_solicitante",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "contracts",
        sa.Column(
            "firma_proveedor",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "contracts",
        sa.Column("firmado_solicitante_en", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "contracts",
        sa.Column("firmado_proveedor_en", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "contracts", sa.Column("datos_firma_solicitante", sa.JSON(), nullable=True)
    )
    op.add_column(
        "contracts", sa.Column("datos_firma_proveedor", sa.JSON(), nullable=True)
    )

    op.create_index(
        "ix_contracts_oferta_id", "contracts", ["oferta_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_contracts_oferta_id", table_name="contracts")
    op.drop_column("contracts", "datos_firma_proveedor")
    op.drop_column("contracts", "datos_firma_solicitante")
    op.drop_column("contracts", "firmado_proveedor_en")
    op.drop_column("contracts", "firmado_solicitante_en")
    op.drop_column("contracts", "firma_proveedor")
    op.drop_column("contracts", "firma_solicitante")
    op.drop_column("contracts", "horario")
    op.drop_column("contracts", "fecha_deseada")
    op.drop_column("contracts", "condiciones")
    op.drop_column("contracts", "monto")
    op.drop_column("contracts", "oferta_id")

    op.drop_column("ofertas", "fecha_aceptacion")
    op.drop_column("ofertas", "condiciones")
    op.drop_column("ofertas", "monto_final")
    op.drop_column("ofertas", "aceptada_por_pds")
    op.drop_column("ofertas", "aceptada_por_solicitante")
    op.drop_column("ofertas", "contra_autor")
