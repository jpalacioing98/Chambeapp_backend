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

        db.session.commit()

        print("\n=== Seed completado ===")
        print(f"Seed completado: {len(created)} usuarios creados")
        if created:
            print("Emails creados:")
            for e in created:
                print(f"  - {e}")
        else:
            print("Ningún usuario nuevo (todos ya existían).")
