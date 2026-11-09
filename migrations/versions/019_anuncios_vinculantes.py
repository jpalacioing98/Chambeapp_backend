"""Anuncios vinculantes: modalidad contrato y trazabilidad de contratos.

- AnuncioLaboral: modalidad (contacto|contrato), presupuesto, fecha_deseada,
  horario, contract_ids e índice por modalidad.
- AnuncioPostulacion: contract_id (contrato generado al contratar).
- Enum de postulaciones: nuevo valor 'contratado' (idempotente sobre los
  dos nombres históricos del tipo en Postgres).

Revision ID: 019_anuncios_vinculantes
Revises: 018_negociacion_bilateral
Create Date: 2026-11-09
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "019_anuncios_vinculantes"
down_revision: Union[str, None] = "018_negociacion_bilateral"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # DDL idempotente: la migración debe ser inocua tanto sobre una base
    # creada por la cadena de migraciones como sobre una creada por
    # `db.create_all()` (el arranque del contenedor usa create_all + stamp).
    op.execute(
        "DO $$ BEGIN CREATE TYPE modalidadanuncio AS ENUM ("
        "'contacto','contrato');"
        " EXCEPTION WHEN duplicate_object THEN null; END $$"
    )
    op.execute(
        "ALTER TABLE anuncios_laborales "
        "ADD COLUMN IF NOT EXISTS modalidad modalidadanuncio "
        "NOT NULL DEFAULT 'contacto'"
    )
    op.execute(
        "ALTER TABLE anuncios_laborales "
        "ADD COLUMN IF NOT EXISTS presupuesto DOUBLE PRECISION"
    )
    op.execute(
        "ALTER TABLE anuncios_laborales "
        "ADD COLUMN IF NOT EXISTS fecha_deseada DATE"
    )
    op.execute(
        "ALTER TABLE anuncios_laborales "
        "ADD COLUMN IF NOT EXISTS horario VARCHAR(80)"
    )
    op.execute(
        "ALTER TABLE anuncios_laborales "
        "ADD COLUMN IF NOT EXISTS contract_ids JSON NOT NULL DEFAULT '[]'::json"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_anuncios_modalidad_creado "
        "ON anuncios_laborales (modalidad, creado_en)"
    )

    # Contrato generado al contratar una postulación.
    op.execute(
        "ALTER TABLE anuncios_postulaciones "
        "ADD COLUMN IF NOT EXISTS contract_id INTEGER"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_anuncios_postulaciones_contract_id "
        "ON anuncios_postulaciones (contract_id)"
    )

    # Enum de postulaciones: valor 'contratado'. El tipo se creó en 013 con
    # el nombre 'estadopostulacion' y el modelo lo crea como
    # 'estadopostulacionanuncio': se cubren ambos nombres.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_type WHERE typname = 'estadopostulacionanuncio'
            ) THEN
                ALTER TYPE estadopostulacionanuncio
                    ADD VALUE IF NOT EXISTS 'contratado';
            END IF;
            IF EXISTS (
                SELECT 1 FROM pg_type WHERE typname = 'estadopostulacion'
            ) THEN
                ALTER TYPE estadopostulacion
                    ADD VALUE IF NOT EXISTS 'contratado';
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS ix_anuncios_postulaciones_contract_id"
    )
    op.execute("ALTER TABLE anuncios_postulaciones DROP COLUMN IF EXISTS contract_id")

    op.execute("DROP INDEX IF EXISTS ix_anuncios_modalidad_creado")
    op.execute("ALTER TABLE anuncios_laborales DROP COLUMN IF EXISTS contract_ids")
    op.execute("ALTER TABLE anuncios_laborales DROP COLUMN IF EXISTS horario")
    op.execute("ALTER TABLE anuncios_laborales DROP COLUMN IF EXISTS fecha_deseada")
    op.execute("ALTER TABLE anuncios_laborales DROP COLUMN IF EXISTS presupuesto")
    op.execute("ALTER TABLE anuncios_laborales DROP COLUMN IF EXISTS modalidad")
    op.execute("DROP TYPE IF EXISTS modalidadanuncio")

