"""Seed script for ChambeApp backend (AUP Implementation).

Uso:
    python seed.py

Crea las tablas (db.create_all) y 6 usuarios de prueba (uno por rol),
idempotente: si el email ya existe, lo omite. Por defecto usa SQLite
(chambeapp.db) vía DevelopmentConfig.
"""

from app import create_app
from app.extensions import db
from app.models.user import User, Profile, LegalAcceptance, RolUsuario, Verification
from app.models.audit import AuditLog  # asegura creación de la tabla en create_all
from app.models.service import Service, EstadoServicio
from app.models.order import Dispute
from app.models.ticket import Ticket
from app.models.payment import Payment
from app.models.config import SystemConfig, FeatureFlag


# Datos exactos de los 6 usuarios semilla (un rol por usuario).
SEED_USERS = [
    {"email": "trabajador@chambeapp.com", "rol": RolUsuario.TRABAJADOR, "nombre": "Trabajador Demo"},
    {"email": "empleador@chambeapp.com", "rol": RolUsuario.EMPLEADOR, "nombre": "Empleador Demo"},
    {"email": "verificador@chambeapp.com", "rol": RolUsuario.VERIFICADOR, "nombre": "Verificador Demo"},
    {"email": "soporte@chambeapp.com", "rol": RolUsuario.SOPORTE, "nombre": "Soporte Demo"},
    {"email": "admin@chambeapp.com", "rol": RolUsuario.ADMIN, "nombre": "Admin Demo"},
    {"email": "superadmin@chambeapp.com", "rol": RolUsuario.SUPERADMIN, "nombre": "Superadmin Demo"},
]

PASSWORD = "ChambeApp123!"
TYC_VERSION = "1.0"
TYC_IP = "127.0.0.1"


def _build_profile(rol: RolUsuario) -> Profile:
    """Construye un Profile con perfil_completo=True según el rol."""
    if rol == RolUsuario.TRABAJADOR:
        return Profile(
            habilidades=["plomería", "jardinería", "electricidad"],
            categorias=["plomería", "jardinería"],
            calificacion_promedio=5.0,
            verificado=True,
            zona="Valledupar",
            perfil_completo=True,
        )
    # Demás roles: mínimo categorias=["plomería"] para perfil_completo=True.
    return Profile(
        habilidades=[],
        categorias=["plomería"],
        calificacion_promedio=0.0,
        verificado=False,
        zona="Valledupar",
        perfil_completo=True,
    )


def seed_users() -> list[str]:
    """Crea los 6 usuarios semilla si no existen. Devuelve emails creados."""
    created = []
    for spec in SEED_USERS:
        email = spec["email"]
        if User.query.filter_by(email=email).first():
            print(f"  SKIP (ya existe): {email}")
            continue

        user = User(
            email=email,
            rol=spec["rol"],
            nombre=spec.get("nombre"),
            edad_verificada=True,
            acepto_tyc=True,
            activo=True,
            status="active",
        )
        user.set_password(PASSWORD)

        profile = _build_profile(spec["rol"])
        user.profile = profile

        db.session.add(user)
        db.session.add(profile)
        db.session.flush()  # obtener user.id para LegalAcceptance

        legal = LegalAcceptance(
            user_id=user.id, version_tyc=TYC_VERSION, ip=TYC_IP
        )
        db.session.add(legal)
        created.append(email)
        print(f"  CREADO: {email} (rol={spec['rol'].value})")
    return created


def seed_sample_service() -> bool:
    """Crea un servicio de ejemplo publicado por el empleador (idempotente)."""
    empleador = User.query.filter_by(email="empleador@chambeapp.com").first()
    if not empleador:
        return False
    if Service.query.filter_by(
        solicitante_id=empleador.id, categoria="plomería"
    ).first():
        print("  SKIP servicio ejemplo (ya existe)")
        return False

    service = Service(
        solicitante_id=empleador.id,
        categoria="plomería",
        descripcion="Reparación de fuga de agua en tubería principal.",
        ubicacion="Valledupar",
        presupuesto=120000,
        estado=EstadoServicio.PUBLICADO,
    )
    db.session.add(service)
    print("  CREADO servicio ejemplo: plomería / Valledupar / $120000")
    return True


def seed_config() -> int:
    """Crea SystemConfig y FeatureFlag por defecto si no existen. Devuelve nº creados."""
    created = 0
    now = "2026-01-01T00:00:00+00:00"

    # --- SystemConfig por defecto ---
    config_defaults = [
        ("commission_rate", "12", "int", "Comisión de plataforma principal (%)"),
        ("commission_rate_alt", "8", "int", "Comisión alternativa (%)"),
        ("escrow_hours", "48", "int", "Horas de auto-liberación de escrow"),
        ("dispute_days", "5", "int", "Días hábiles para abrir disputa"),
        ("volume_discount", "10", "int", "Descuento por volumen (%)"),
        (
            "plans",
            '{"free": {"price": 0, "features": ["1 servicio"]}, '
            '"pro": {"price": 19900, "features": ["servicios ilimitados"]}}',
            "json",
            "Planes de suscripción (monedas/pesos)",
        ),
        (
            "tyc_current",
            '{"version": 1, "content": "Términos y Condiciones v1 de ChambeApp.", '
            f'"published_at": "{now}"}}',
            "json",
            "Términos y Condiciones vigentes",
        ),
        (
            "ai_weights",
            '{"w_price": 0.4, "w_rating": 0.3, "w_distance": 0.3}',
            "json",
            "Pesos del modelo de recomendación IA",
        ),
    ]
    for key, value, vtype, desc in config_defaults:
        if SystemConfig.query.filter_by(key=key).first():
            print(f"  SKIP config (ya existe): {key}")
            continue
        cfg = SystemConfig(
            key=key, value=value, value_type=vtype, description=desc,
            updated_by=None,
        )
        db.session.add(cfg)
        created += 1
        print(f"  CREADO config: {key} ({vtype})")

    # --- FeatureFlag por defecto ---
    flag_defaults = [
        ("module_3d", False, "Módulo 3D/360 de portfolios"),
        ("certificados", False, "Certificados de verificación avanzada"),
        ("cobertura_valledupar", True, "Cobertura habilitada en Valledupar"),
        ("mantenimiento", False, "Modo mantenimiento de la plataforma"),
    ]
    for key, enabled, desc in flag_defaults:
        if FeatureFlag.query.filter_by(key=key).first():
            print(f"  SKIP flag (ya existe): {key}")
            continue
        flag = FeatureFlag(key=key, enabled=enabled, description=desc)
        db.session.add(flag)
        created += 1
        print(f"  CREADO flag: {key} = {enabled}")

    return created


if __name__ == "__main__":
    app = create_app()  # DevelopmentConfig -> sqlite:///chambeapp.db
    with app.app_context():
        print("Recreando esquema (db.drop_all + db.create_all)...")
        # Dev/MVP: recrea el esquema para reflejar nuevos modelos/campos.
        # ¡Borra datos de dev! Esperado en esta fase.
        db.drop_all()
        db.create_all()

        print("Sembrando usuarios...")
        created = seed_users()
        seed_sample_service()
        print("Sembrando configuración global y feature flags...")
        seed_config()

        db.session.commit()

        print("\n=== Seed completado ===")
        print(f"Seed completado: {len(created)} usuarios creados")
        if created:
            print("Emails creados:")
            for e in created:
                print(f"  - {e}")
        else:
            print("Ningún usuario nuevo (todos ya existían).")
