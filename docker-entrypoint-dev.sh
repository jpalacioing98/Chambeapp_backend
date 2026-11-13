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
    # Solicitudes: horario preferido + fotos adjuntas (idempotente, complementa
    # la migración 003 sin re-ejecutar create_table).
    run("ALTER TABLE solicitudes ADD COLUMN IF NOT EXISTS horario VARCHAR(80)")
    run("ALTER TABLE solicitudes ADD COLUMN IF NOT EXISTS imagenes JSON")
    # Negociaci�n bilateral (migraci�n 018): aceptaci�n por ambas partes,
    # valor final, condiciones y firmas paralelas del contrato.
    run("ALTER TABLE ofertas ADD COLUMN IF NOT EXISTS contra_autor VARCHAR(20)")
    run("ALTER TABLE ofertas ADD COLUMN IF NOT EXISTS aceptada_por_solicitante BOOLEAN NOT NULL DEFAULT FALSE")
    run("ALTER TABLE ofertas ADD COLUMN IF NOT EXISTS aceptada_por_pds BOOLEAN NOT NULL DEFAULT FALSE")
    run("ALTER TABLE ofertas ADD COLUMN IF NOT EXISTS monto_final DOUBLE PRECISION")
    run("ALTER TABLE ofertas ADD COLUMN IF NOT EXISTS condiciones JSON")
    run("ALTER TABLE ofertas ADD COLUMN IF NOT EXISTS fecha_aceptacion TIMESTAMP WITH TIME ZONE")
    run("ALTER TABLE contracts ADD COLUMN IF NOT EXISTS oferta_id INTEGER")
    run("ALTER TABLE contracts ADD COLUMN IF NOT EXISTS monto DOUBLE PRECISION")
    run("ALTER TABLE contracts ADD COLUMN IF NOT EXISTS condiciones JSON")
    run("ALTER TABLE contracts ADD COLUMN IF NOT EXISTS fecha_deseada DATE")
    run("ALTER TABLE contracts ADD COLUMN IF NOT EXISTS horario VARCHAR(80)")
    run("ALTER TABLE contracts ADD COLUMN IF NOT EXISTS firma_solicitante BOOLEAN NOT NULL DEFAULT FALSE")
    run("ALTER TABLE contracts ADD COLUMN IF NOT EXISTS firma_proveedor BOOLEAN NOT NULL DEFAULT FALSE")
    run("ALTER TABLE contracts ADD COLUMN IF NOT EXISTS firmado_solicitante_en TIMESTAMP WITH TIME ZONE")
    run("ALTER TABLE contracts ADD COLUMN IF NOT EXISTS firmado_proveedor_en TIMESTAMP WITH TIME ZONE")
    run("ALTER TABLE contracts ADD COLUMN IF NOT EXISTS datos_firma_solicitante JSON")
    run("ALTER TABLE contracts ADD COLUMN IF NOT EXISTS datos_firma_proveedor JSON")
    run("CREATE INDEX IF NOT EXISTS ix_contracts_oferta_id ON contracts (oferta_id)")
    # Barrido 360: la equirectangular va como data URL (cientos de KB) → TEXT
    run("ALTER TABLE solicitudes ALTER COLUMN imagen_360 TYPE TEXT")
    # Pago directo: sin retencion de fondos. Drop idempotente de columnas.
    run("ALTER TABLE payments DROP COLUMN IF EXISTS liberado_en")
    run("ALTER TABLE disputes DROP COLUMN IF EXISTS payment_action")
    # Disputas durante la negociacion (aun sin contrato): se ligan a la
    # solicitud/oferta y contract_id pasa a ser opcional.
    run("ALTER TABLE disputes ALTER COLUMN contract_id DROP NOT NULL")
    run("ALTER TABLE disputes ADD COLUMN IF NOT EXISTS solicitud_id INTEGER")
    run("ALTER TABLE disputes ADD COLUMN IF NOT EXISTS oferta_id INTEGER")
    run("ALTER TABLE disputes ADD COLUMN IF NOT EXISTS chat_habilitado BOOLEAN NOT NULL DEFAULT FALSE")
    run("ALTER TABLE disputes ADD COLUMN IF NOT EXISTS chat_habilitado_solicitante BOOLEAN NOT NULL DEFAULT FALSE")
    run("ALTER TABLE disputes ADD COLUMN IF NOT EXISTS chat_habilitado_proveedor BOOLEAN NOT NULL DEFAULT FALSE")
    run("ALTER TABLE messages ADD COLUMN IF NOT EXISTS es_soporte BOOLEAN NOT NULL DEFAULT FALSE")
    run("ALTER TABLE disputes ADD COLUMN IF NOT EXISTS decision_estado VARCHAR(20)")
    run("ALTER TABLE disputes ADD COLUMN IF NOT EXISTS decision_solicitante VARCHAR(20)")
    run("ALTER TABLE disputes ADD COLUMN IF NOT EXISTS decision_proveedor VARCHAR(20)")
    run("ALTER TABLE disputes ADD COLUMN IF NOT EXISTS decision_message_id INTEGER")
    run("ALTER TABLE disputes ADD COLUMN IF NOT EXISTS negociacion_cerrada BOOLEAN NOT NULL DEFAULT FALSE")
    run("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS oculta BOOLEAN NOT NULL DEFAULT FALSE")
    run("UPDATE disputes SET chat_habilitado_solicitante = TRUE, chat_habilitado_proveedor = TRUE WHERE chat_habilitado = TRUE")
    run("CREATE INDEX IF NOT EXISTS ix_disputes_solicitud_creado ON disputes (solicitud_id, created_at)")
    # Recrear el enum estadopago sin el valor CONFIRMADO ("en garantia").
    run(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT 1 FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
        "WHERE t.typname = 'estadopago' AND e.enumlabel = 'CONFIRMADO') THEN "
        "UPDATE payments SET estado = 'COMPLETADO' WHERE estado::text = 'CONFIRMADO'; "
        "ALTER TYPE estadopago RENAME TO estadopago_old; "
        "CREATE TYPE estadopago AS ENUM ('PENDIENTE','COMPLETADO','REEMBOLSADO','FALLIDO'); "
        "ALTER TABLE payments ALTER COLUMN estado TYPE estadopago USING estado::text::estadopago; "
        "DROP TYPE estadopago_old; "
        "END IF; END $$;"
    )
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
    # Migracion 020 (el dev hace `flask db stamp`, no `upgrade`, asi que las
    # migraciones no se ejecutan): bandera maestra de la cascada encendida y
    # radios/esperas nuevos en las cascadas activas.
    run(
        "UPDATE feature_flags SET enabled = true, "
        "description = 'Activa notificaciones en cascada y aviso a PDS elegibles' "
        "WHERE key = 'cascade_notifications'"
    )
    import json as _json
    _nueva_config = _json.dumps([
        {"radius_km": 20.0, "delay_seconds": 30, "max_candidates": 20},
        {"radius_km": 50.0, "delay_seconds": 120, "max_candidates": 40},
        {"radius_km": 100.0, "delay_seconds": 300, "max_candidates": 80},
    ])
    run(
        "UPDATE notification_cascades SET config_json = '" + _nueva_config + "' "
        "WHERE estado = 'activa'"
    )
    print("[dev] PostGIS/flags listos.")

    # Migración 025: suscripciones Web Push (el dev hace stamp, no upgrade).
    run(
        "CREATE TABLE IF NOT EXISTS push_subscriptions ("
        "id SERIAL PRIMARY KEY, "
        "user_id INTEGER NOT NULL REFERENCES users(id), "
        "endpoint TEXT NOT NULL UNIQUE, "
        "p256dh TEXT NOT NULL, "
        "auth TEXT NOT NULL, "
        "user_agent VARCHAR(255), "
        "creado_en TIMESTAMP NOT NULL DEFAULT NOW(), "
        "actualizado_en TIMESTAMP NOT NULL DEFAULT NOW())"
    )
    run(
        "CREATE INDEX IF NOT EXISTS ix_push_subscriptions_user "
        "ON push_subscriptions (user_id)"
    )

    # Migración 026: 2FA por método + códigos de recuperación.
    run("ALTER TABLE users ADD COLUMN IF NOT EXISTS two_factor_method VARCHAR(10) NOT NULL DEFAULT 'sms'")
    run("ALTER TABLE users ADD COLUMN IF NOT EXISTS two_factor_secret VARCHAR(255)")
    run("ALTER TABLE users ADD COLUMN IF NOT EXISTS two_factor_pending_secret VARCHAR(255)")
    run("ALTER TABLE users ADD COLUMN IF NOT EXISTS two_factor_confirmed_at TIMESTAMP")
    # Preferencias UI: mapa inicial de chambas (2d | 3d).
    run("ALTER TABLE merchant_preferences ADD COLUMN IF NOT EXISTS mapa_preferido VARCHAR(4) NOT NULL DEFAULT '2d'")
    # Portafolio: datos visibles de la card y galería del trabajo.
    run("ALTER TABLE portfolio_items ADD COLUMN IF NOT EXISTS precio INTEGER")
    run("ALTER TABLE portfolio_items ADD COLUMN IF NOT EXISTS calificacion DOUBLE PRECISION")
    run("ALTER TABLE portfolio_items ADD COLUMN IF NOT EXISTS resena_texto TEXT")
    run("ALTER TABLE portfolio_items ADD COLUMN IF NOT EXISTS resena_autor VARCHAR(120)")
    run("ALTER TABLE portfolio_items ADD COLUMN IF NOT EXISTS antes JSON NOT NULL DEFAULT '[]'::json")
    run("ALTER TABLE portfolio_items ADD COLUMN IF NOT EXISTS despues JSON NOT NULL DEFAULT '[]'::json")
    run("ALTER TABLE portfolio_items ADD COLUMN IF NOT EXISTS galeria JSON NOT NULL DEFAULT '[]'::json")
    run(
        "CREATE TABLE IF NOT EXISTS two_factor_recovery_codes ("
        "id SERIAL PRIMARY KEY, "
        "user_id INTEGER NOT NULL REFERENCES users(id), "
        "code_hash VARCHAR(64) NOT NULL, "
        "usado BOOLEAN NOT NULL DEFAULT FALSE, "
        "usado_en TIMESTAMP, "
        "creado_en TIMESTAMP NOT NULL DEFAULT NOW(), "
        "CONSTRAINT uq_2fa_recovery_user_code UNIQUE (user_id, code_hash))"
    )
    run(
        "CREATE INDEX IF NOT EXISTS ix_2fa_recovery_user "
        "ON two_factor_recovery_codes (user_id)"
    )
    # VAPID: genera claves UNA vez si pywebpush/py-vapid están instalados.
    try:
        from app.models.config import SystemConfig
        if not SystemConfig.get_value("vapid_public_key"):
            try:
                import base64
                from py_vapid import Vapid01
                from cryptography.hazmat.primitives import serialization
                _v = Vapid01()
                _v.generate_keys()
                _pub_bytes = _v.public_key.public_bytes(
                    serialization.Encoding.X962,
                    serialization.PublicFormat.UncompressedPoint,
                )
                _pub = base64.urlsafe_b64encode(_pub_bytes).rstrip(b"=").decode()
                _priv = _v.private_pem()
                if isinstance(_priv, bytes):
                    _priv = _priv.decode()
                SystemConfig.set_value("vapid_public_key", _pub)
                SystemConfig.set_value("vapid_private_key", _priv)
                print("[dev] Claves VAPID generadas.")
            except Exception as _e:
                print(f"  (aviso) VAPID no generado: {_e}")
    except Exception as _e:
        print(f"  (aviso) VAPID: {_e}")
PY

# Registrar migraciones como aplicadas (el esquema ya está completo).
echo "[dev] Registrando migraciones (flask db stamp head)..."
flask db stamp head || echo "[dev] (aviso) stamp falló; las migraciones no se marcaron."

echo "[dev] Iniciando backend en modo desarrollo (run.py)..."
exec python run.py
