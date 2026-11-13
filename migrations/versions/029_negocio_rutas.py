"""negocios ambulantes: modalidad + rutas de recorrido

Revision ID: 029_negocio_rutas
Revises: 028_billetera_monedas
Create Date: 2026-11-12

- `negocios.modalidad`: estatico | ambulante.
- Tabla `negocio_rutas`: trazado (puntos JSON), calles, color, activa,
  en_curso y progreso del recorrido actual.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "029_negocio_rutas"
down_revision: Union[str, None] = "028_billetera_monedas"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "negocios",
        sa.Column(
            "modalidad",
            sa.String(length=20),
            nullable=False,
            server_default="estatico",
        ),
    )

    op.create_table(
        "negocio_rutas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "negocio_id",
            sa.Integer(),
            sa.ForeignKey("negocios.id"),
            nullable=False,
        ),
        sa.Column("nombre", sa.String(length=80), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("puntos", sa.JSON(), nullable=False),
        sa.Column("calles", sa.JSON(), nullable=False),
        sa.Column("color", sa.String(length=9), nullable=True),
        sa.Column(
            "activa",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "en_curso",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "progreso",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("creado_en", sa.DateTime(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_negocio_rutas_negocio_id",
        "negocio_rutas",
        ["negocio_id"],
    )
    op.create_index(
        "ix_negocio_rutas_negocio_en_curso",
        "negocio_rutas",
        ["negocio_id", "en_curso"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_negocio_rutas_negocio_en_curso",
        table_name="negocio_rutas",
    )
    op.drop_index(
        "ix_negocio_rutas_negocio_id",
        table_name="negocio_rutas",
    )
    op.drop_table("negocio_rutas")
    op.drop_column("negocios", "modalidad")
