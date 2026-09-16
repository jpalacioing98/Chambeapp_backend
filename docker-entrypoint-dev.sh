#!/bin/sh
# Entrypoint de desarrollo ChambeApp backend.
# Orden robusto para dev:
#   1. Espera a PostgreSQL.
#   2. Si la base está vacía -> python seed.py (create_all + datos de ejemplo).
#   3. PostGIS + columna geom + feature flags ML (idempotente, complementa migraciones).
#   4. flask db stamp head (registra migraciones sin re-ejecutar create_table conflictivo).
#   5. Arranca el backend con hot-reload (run.py).
set -e

echo "[dev] Esperando PostgreSQL (db:5432)..."
i=0
until python - <<'PY' 2>/dev/null
import socket
s = socket.socket(); s.settimeout(2)
try:
    s.connect(('db', 5432)); s.close(); raise SystemExit(0)
except OSError:
    raise SystemExit(1)
PY
do
  i=$((i+1))
  if [ "$i" -gt 30 ]; then echo "[dev] ERROR: PostgreSQL no respondió tras 60s"; exit 1; fi
  printf "[dev]   esperando DB (%s)...\n" "$i"
  sleep 2
done
echo "[dev] PostgreSQL listo."

export FLASK_APP=run.py

# ¿Base vacía? (sin tabla users o sin filas) -> sembrar esquema + datos.
NEEDS_SEED=$(python - <<'PY'
from app import create_app
from app.extensions import db
app = create_app()
with app.app_context():
    try:
        n = db.session.execute(db.text("SELECT COUNT(*) FROM users")).scalar() or 0
        print("1" if n == 0 else "0")
    except Exception:
        print("1")
PY
)

if [ "$NEEDS_SEED" = "1" ]; then
  echo "[dev] Base vacía: ejecutando seed.py (create_all + datos de ejemplo)..."
  python seed.py
else
  echo "[dev] Base ya con datos: se omite seed.py."
fi

# PostGIS + columna geom + feature flags ML (idempotente). Complementa las
# migraciones sin usar alembic (trust_scores ya lo crea create_all).
echo "[dev] Aplicando extensiones/índices PostGIS (idempotente)..."
python - <<'PY'
from app import create_app
from app.extensions import db
app = create_app()
with app.app_context():
    def run(sql):
        try:
            db.session.execute(db.text(sql))
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"  (omitido) {sql[:70]} -> {e}")
    run("CREATE EXTENSION IF NOT EXISTS postgis")
    run("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS geom geometry(POINT, 4326)")
    # Backfill de coordenadas (dev: Valledupar) y poblado de geom desde lat/long.
    run("UPDATE profiles SET latitud = 10.4806, longitud = -73.2495 WHERE latitud IS NULL OR longitud IS NULL")
    run("UPDATE profiles SET geom = ST_SetSRID(ST_MakePoint(longitud, latitud), 4326) WHERE latitud IS NOT NULL AND longitud IS NOT NULL")
    try:
        db.session.execute(db.text("CREATE INDEX IF NOT EXISTS idx_profiles_geom ON profiles USING GIST (geom)"))
        db.session.commit()
    except Exception as e:
        db.session.rollback(); print(f"  (omitido) indice geom -> {e}")
    ml_flags = [
        ("ml_ranking_enabled", False, "Activa el ranking ML (LightGBM)"),
        ("ml_shadow_mode", True, "Log ML pero usa heurístico"),
        ("cascade_notifications", False, "Activa notificaciones en cascada"),
        ("portfolio_upload", False, "Activa upload de portafolio"),
        ("thompson_sampling", False, "Activa rotación con Bandit"),
    ]
    for key, enabled, desc in ml_flags:
        run(
            "INSERT INTO feature_flags (key, enabled, description) VALUES "
            f"('{key}', {str(enabled).lower()}, '{desc}') ON CONFLICT (key) DO NOTHING"
        )
    print("[dev] PostGIS/flags listos.")
PY

# Registrar migraciones como aplicadas (el esquema ya está completo).
echo "[dev] Registrando migraciones (flask db stamp head)..."
flask db stamp head || echo "[dev] (aviso) stamp falló; las migraciones no se marcaron."

echo "[dev] Iniciando backend en modo desarrollo (run.py)..."
exec python run.py
