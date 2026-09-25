"""Crea la tabla trust_scores (idempotente) si no existe.

Revision ID: 006_create_trust_scores
Revises: 005_add_merchant_to_rol_enum
Create Date: 2026-09-17

Contexto:
  La migración 001_add_postgis_trust crea trust_scores, pero el entrypoint de
  dev (docker-entrypoint-dev.sh) usa `flask db stamp head` en vez de
  `flask db upgrade`, y seed.py ejecuta `db.drop_all()` + `db.create_all()`
  SIN importar app.models.trust. Resultado: en la BD del contenedor la tabla
  trust_scores NO existe y `GET /api/v1/trust/<id>` devuelve 500
  (relation "trust_scores" does not exist).

  Esta migración es idempotente: si la tabla ya existe (p.ej. creada por
  create_all en un seed fresco), no hace nada. El tipo enum trust_level se
  crea con guarda EXCEPTION WHEN duplicate_object (patrón de la migración 004).

  NOTA de implementación: se usa SQL crudo en vez de op.create_table porque
  Alembic 1.20.0 + SQLAlchemy 2.0.52 emiten `CREATE TYPE` para columnas
  sa.Enum aunque se pase create_type=False (evento _on_table_create), lo que
  rompe la idempotencia cuando el tipo ya existe.

downgrade():
  Elimina la tabla y el tipo enum trust_level (solo si existen).
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '006_create_trust_scores'
down_revision = '005_add_merchant_to_rol_enum'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "trust_scores" in inspector.get_table_names():
        return  # ya existe (create_all de seed.py la creó)

    # Crear tipo enum trust_level si no existe (idempotente).
    op.execute("""
        DO $$
        BEGIN
            CREATE TYPE trust_level AS ENUM
                ('nuevo', 'confiable', 'verificado', 'experto');
        EXCEPTION WHEN duplicate_object THEN null;
        END$$;
    """)

    # Tabla trust_scores (espejo del modelo app/models/trust.py).
    op.execute("""
        CREATE TABLE trust_scores (
            id SERIAL PRIMARY KEY,
            pds_id INTEGER NOT NULL UNIQUE REFERENCES users(id),
            kyc_verificado BOOLEAN DEFAULT FALSE,
            portfolio_calidad FLOAT DEFAULT 0.0,
            rating_score FLOAT DEFAULT 0.0,
            contratos_completados INTEGER DEFAULT 0,
            referidos_count INTEGER DEFAULT 0,
            puntuacion FLOAT DEFAULT 0.0,
            nivel trust_level DEFAULT 'nuevo',
            componentes_json JSON,
            calculado_en TIMESTAMP DEFAULT now(),
            version INTEGER DEFAULT 1
        )
    """)
    op.execute("CREATE INDEX ix_trust_scores_pds_id ON trust_scores (pds_id)")
    op.execute("CREATE INDEX ix_trust_scores_nivel ON trust_scores (nivel)")
    op.execute("CREATE INDEX ix_trust_scores_puntuacion ON trust_scores (puntuacion)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_trust_scores_puntuacion")
    op.execute("DROP INDEX IF EXISTS ix_trust_scores_nivel")
    op.execute("DROP INDEX IF EXISTS ix_trust_scores_pds_id")
    op.execute("DROP TABLE IF EXISTS trust_scores")
    op.execute("DROP TYPE IF EXISTS trust_level")