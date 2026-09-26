"""Seed script for ChambeApp backend (AUP Implementation)."""

from datetime import date, datetime, timedelta, timezone

from app import create_app
from app.extensions import db
from app.models.user import User, Profile, LegalAcceptance, RolUsuario
from app.models.solicitud import Solicitud, EstadoSolicitud, UrgenciaSolicitud
from app.models.oferta import Oferta, EstadoOferta
from app.models.contract import Dispute, Contract, EstadoContrato
from app.models.negocio import Negocio, NegocioHorario
from app.models.config import SystemConfig, FeatureFlag
from app.models.kyc import DocumentoRequerido
from app.models.merchant import MerchantPreference
from app.data.tyc import TYC_CONTENT, TYC_VERSION
from app.data.seed_kyc_merchant import seed_kyc_merchant

PASSWORD = "ChambeApp123!"
TYC_IP = "127.0.0.1"

SEED_USERS = [
    {"email": "pds@chambeapp.com", "rol": RolUsuario.PDS, "nombre": "Trabajador Demo"},
    {"email": "solicitante@chambeapp.com", "rol": RolUsuario.SOLICITANTE, "nombre": "Empleador Demo"},
    {"email": "merchant@chambeapp.com", "rol": RolUsuario.MERCHANT, "nombre": "Comerciante Demo"},
    {"email": "verificador@chambeapp.com", "rol": RolUsuario.VERIFICADOR, "nombre": "Verificador Demo"},
    {"email": "soporte@chambeapp.com", "rol": RolUsuario.SOPORTE, "nombre": "Soporte Demo"},
    {"email": "admin@chambeapp.com", "rol": RolUsuario.ADMIN, "nombre": "Admin Demo"},
    {"email": "superadmin@chambeapp.com", "rol": RolUsuario.SUPERADMIN, "nombre": "Super Admin Demo"},
]

def _build_profile(rol: RolUsuario) -> Profile:
    """Construye un Profile con perfil_completo=True según el rol."""
    if rol == RolUsuario.PDS:
        return Profile(
            habilidades=["plomería", "jardinería", "electricidad"],
            categorias=["plomería", "jardinería"],
            calificacion_promedio=5.0,
            verificado=True,
            zona="Valledupar",
            latitud=10.4806,
            longitud=-73.2495,
            perfil_completo=True,
        )
    # Demás roles: mínimo categorias=["plomería"] para perfil_completo=True.
    return Profile(
        habilidades=[],
        categorias=["plomería"],
        calificacion_promedio=0.0,
        verificado=False,
        zona="Valledupar",
        latitud=10.4806,
        longitud=-73.2495,
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
    """Crea una solicitud de ejemplo publicada por el empleador (idempotente)."""
    empleador = User.query.filter_by(email="solicitante@chambeapp.com").first()
    if not empleador:
        return False
    if Solicitud.query.filter_by(
        solicitante_id=empleador.id, categoria="plomería"
    ).first():
        print("  SKIP solicitud ejemplo (ya existe)")
        return False

    solicitud = Solicitud(
        solicitante_id=empleador.id,
        titulo="Fuga de agua en baño principal",
        categoria="plomería",
        descripcion="Reparación de fuga de agua en tubería principal.",
        ubicacion="Valledupar",
        presupuesto=120000,
        fecha_deseada=date.today() + timedelta(days=2),
        urgencia=UrgenciaSolicitud.SEMANA,
        estado=EstadoSolicitud.PUBLICADO,
    )
    db.session.add(solicitud)
    print("  CREADA solicitud ejemplo: plomería / Valledupar / $120000")
    return True


def seed_sample_oferta() -> bool:
    """Crea una solicitud de ejemplo del empleador y una oferta del pds (idempotente)."""
    empleador = User.query.filter_by(email="solicitante@chambeapp.com").first()
    trabajador = User.query.filter_by(email="pds@chambeapp.com").first()
    if not empleador or not trabajador:
        return False

    solicitud = Solicitud.query.filter_by(
        solicitante_id=empleador.id,
        descripcion="Instalación de mueble de cocina.",
    ).first()
    if solicitud is None:
        solicitud = Solicitud(
            solicitante_id=empleador.id,
            titulo="Instalación de mueble de cocina",
            categoria="carpintería",
            descripcion="Instalación de mueble de cocina.",
            ubicacion="Valledupar",
            presupuesto=150000,
            estado=EstadoSolicitud.PUBLICADO,
        )
        db.session.add(solicitud)
        db.session.flush()
        print("  CREADA solicitud ejemplo (empleador): carpintería / $150000")

    if Oferta.query.filter_by(
        solicitud_id=solicitud.id, pds_id=trabajador.id
    ).first():
        print("  SKIP oferta ejemplo (ya existe)")
        return False

    oferta = Oferta(
        solicitud_id=solicitud.id,
        pds_id=trabajador.id,
        monto=140000,
        mensaje="Puedo instalarlo mañana sin problema.",
        estado=EstadoOferta.PENDIENTE.value,
    )
    db.session.add(oferta)
    print("  CREADA oferta ejemplo (pds): $140000 sobre solicitud de ejemplo")
    return True


def seed_sample_contract() -> bool:
    """Crea un contrato de ejemplo en 'en_progreso' (capeta iniciada) con inicio_en.

    Idempotente: si ya existe un contrato para la solicitud plomería del empleador
    con el trabajador como pds, lo omite.
    """
    empleador = User.query.filter_by(email="solicitante@chambeapp.com").first()
    trabajador = User.query.filter_by(email="pds@chambeapp.com").first()
    if not empleador or not trabajador:
        return False

    solicitud = Solicitud.query.filter_by(
        solicitante_id=empleador.id, categoria="plomería"
    ).first()
    if solicitud is None:
        print("  SKIP contract ejemplo (falta solicitud plomería)")
        return False

    if Contract.query.filter_by(
        service_id=solicitud.id, proveedor_id=trabajador.id
    ).first():
        print("  SKIP contract ejemplo (ya existe)")
        return False

    contract = Contract(
        service_id=solicitud.id,
        proveedor_id=trabajador.id,
        solicitante_id=empleador.id,
        estado=EstadoContrato.EN_PROGRESO,
        inicio_en=datetime.now(timezone.utc),
    )
    db.session.add(contract)
    print("  CREADO contract ejemplo (capeta): en_progreso con inicio_en seteado")
    return True


def seed_merchant_business() -> bool:
    """Crea un negocio demo para el merchant semilla (idempotente).

    Crea un negocio 'Restaurante El Sazón' con horarios e imágenes de ejemplo.
    """
    merchant = User.query.filter_by(email="merchant@chambeapp.com").first()
    if not merchant:
        return False
    if Negocio.query.filter_by(owner_id=merchant.id).first():
        print("  SKIP negocio merchant demo (ya existe)")
        return False

    from app.services.negocio_utils import generar_slug

    slug = generar_slug("Restaurante El Sazón")
    negocio = Negocio(
        owner_id=merchant.id,
        slug=slug,
        nombre="Restaurante El Sazón",
        descripcion="Restaurante tradicional colombiano en El Poblado, Medellín.",
        tipo="comercio",
        latitud=6.2138,
        longitud=-75.5689,
        direccion="Calle 10 #43-14, El Poblado, Medellín",
        ciudad="Medellin",
        departamento="Antioquia",
        categoria_principal="gastronomia",
        categorias_secundarias=["bebidas", "postres"],
        servicios=[
            {"titulo": "Comida a la mesa", "descripcion": "Platos típicos colombianos en el local."},
            {"titulo": "Para llevar", "descripcion": "Empaque y pedidos por mostrador."},
        ],
        palabras_clave=["comida colombiana", "restaurante", "medellin"],
        estado="activo",
        verificado=True,
    )
    db.session.add(negocio)
    db.session.flush()

    # Crear horarios: lunes a viernes abiertos, sáb-dom cerrados
    for dia in range(7):
        abierto = dia < 5  # lunes(0) a viernes(4)
        h = NegocioHorario(
            negocio_id=negocio.id,
            dia_semana=dia,
            abierto=abierto,
            hora_apertura="08:00" if abierto else None,
            hora_cierre="20:00" if abierto else None,
        )
        db.session.add(h)

    # Crear preferencias por defecto
    prefs = MerchantPreference(user_id=merchant.id)
    db.session.add(prefs)

    print("  CREADO negocio demo: Restaurante El Sazón (merchant@chambeapp.com)")
    return True


def seed_user_regions() -> int:
    """Asigna la región 'caribe' (Valledupar/Cesar) a los usuarios semilla.

    Los usuarios semilla tienen `zona='Valledupar'`; se les fija la región
    Caribe explícitamente (assign_region no reasigna personal interno).
    """
    from app.models.region import Region
    caribe = Region.query.filter_by(clave="caribe").first()
    if caribe is None:
        print("  SKIP regiones (catálogo no sembrado)")
        return 0
    count = 0
    for spec in SEED_USERS:
        user = User.query.filter_by(email=spec["email"]).first()
        if user and user.region_id is None:
            user.region_id = caribe.id
            count += 1
            print(f"  REGIÓN caribe → {user.email}")
    if count:
        db.session.commit()
    return count


def seed_config() -> int:
    """Crea SystemConfig y FeatureFlag por defecto si no existen. Devuelve nº creados."""
    created = 0
    now = "2026-01-01T00:00:00+00:00"

    # --- SystemConfig por defecto ---
    config_defaults = [
        ("commission_rate", "12", "int", "Comisión de plataforma principal (%)"),
        ("commission_rate_alt", "8", "int", "Comisión alternativa (%)"),
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
            SystemConfig.serialize_value(
                {
                    "version": TYC_VERSION,
                    "content": TYC_CONTENT,
                    "published_at": now,
                },
                "json",
            ),
            "json",
            "Términos y Condiciones vigentes",
        ),
        (
            "ai_weights",
            '{"w_price": 0.4, "w_rating": 0.3, "w_distance": 0.3}',
            "json",
            "Pesos del modelo de recomendación IA",
        ),
        (
            "ciudad_base",
            "Medellin",
            "string",
            "Ciudad base de operación (geofence de solicitudes)",
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

    # --- Actualiza T&C si la versión cambió (re-publicación) ---
    tyc_cfg = SystemConfig.query.filter_by(key="tyc_current").first()
    if tyc_cfg is not None:
        try:
            actual = SystemConfig.parse_value(tyc_cfg.value, "json") or {}
            if actual.get("version") != TYC_VERSION:
                tyc_cfg.value = SystemConfig.serialize_value(
                    {
                        "version": TYC_VERSION,
                        "content": TYC_CONTENT,
                        "published_at": now,
                    },
                    "json",
                )
                created += 1
                print(f"  ACTUALIZADO tyc_current → v{TYC_VERSION}")
        except Exception:
            pass

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


def seed_kyc() -> int:
    """Siembra el catálogo de documentos KYC requeridos por rol.

    El catálogo canónico vive en app/data/seed_kyc.py; esta función solo
    lo sincroniza (inserta faltantes y PODA obsoletos, p. ej.
    "validacion_pago" del solicitante).
    """
    from app.data.seed_kyc import sync_kyc_catalog
    return sync_kyc_catalog()


def seed_habilidades() -> int:
    """Siembra/actualiza el CATÁLOGO NACIONAL de OFICIOS con competencias
    ampliadas y rutas certificables (CUOC / SENA).

    Fuente: app/data/seed_habilidades.py — categorías del catálogo nacional,
    20 oficios con sus competencias y niveles (quiz >=80% + certificación).
    """
    from app.data.seed_habilidades import CATALOGO_OFICIOS, build_niveles
    from app.models.habilidad import Habilidad

    # Nombres cortos usados en catálogos sembrados antes del rediseño →
    # nombres COMPLETOS del documento (CUOC/SENA). Se renombran los oficios
    # existentes (mismo id → no se rompen referencias).
    LEGACY = {
        "Plomería": "Plomería y Fontanería",
        "Electricidad": "Electricidad Residencial y Comercial",
        "Albañilería": "Albañilería, Mampostería y Cimentación",
        "Pintura": "Pintura, Impermeabilización y Acabados",
        "Carpintería": "Carpintería en Madera, MDF y RH (Mueble Fijo y RTA)",
        "Soldadura": "Soldadura, Metalmecánica y Carpintería Metálica",
        "Aire Acondicionado": "Mantenimiento e Instalación de Aire Acondicionado y Climatización",
        "Electrodomésticos": "Reparación y Mantenimiento de Electrodomésticos",
        "Redes y CCTV": "Técnico en Redes, CCTV y Soporte Informático",
        "Jardinería": "Jardinería, Paisajismo y Zonas Verdes",
        "Aseo": "Aseo, Limpieza General y Mantenimiento de Espacios",
        "Cuidado de personas": "Cuidado de Personas y Auxiliar Doméstico",
        "Mudanzas": "Mudanzas, Acarreos y Manejo de Carga Liviana",
        "Barbería": "Barbería, Peluquería y Estilismo",
        "Manicura": "Manicura, Pedicura y Estética de Uñas",
        "Estética facial": "Estética Facial y Corporal (No Invasiva)",
        "Mecánica rápida": "Mecánica Rápida de Automóviles",
        "Mecánica de motos": "Mecánica y Mantenimiento de Motocicletas",
    }

    cambios = 0
    for categoria, nombre, descripcion, competencias, quiz_preguntas in CATALOGO_OFICIOS:
        existente = Habilidad.query.filter_by(nombre=nombre).first()
        if existente is None:
            # Busca el nombre corto previo y lo RENOMBRA (mismo id).
            corto = next((k for k, v in LEGACY.items() if v == nombre), None)
            if corto:
                existente = Habilidad.query.filter_by(nombre=corto).first()
                if existente:
                    existente.nombre = nombre

        niveles = build_niveles(quiz_preguntas)
        if existente:
            if (existente.habilidades != competencias
                    or existente.categoria != categoria
                    or existente.descripcion != descripcion):
                existente.habilidades = competencias
                existente.categoria = categoria
                existente.descripcion = descripcion
                existente.niveles = niveles
                db.session.add(existente)
                cambios += 1
                print(f"  ACTUALIZADO oficio: {nombre} ({categoria})")
            continue
        db.session.add(
            Habilidad(
                nombre=nombre,
                descripcion=descripcion,
                categoria=categoria,
                habilidades=competencias,
                niveles=niveles,
            )
        )
        cambios += 1
        print(f"  CREADO oficio: {nombre} ({categoria}, {len(competencias)} competencias)")
    db.session.commit()
    return cambios


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
        seed_user_regions()
        seed_sample_service()
        seed_sample_oferta()
        seed_sample_contract()
        print("Sembrando negocio y preferencias del merchant demo...")
        seed_merchant_business()
        print("Sembrando configuración global y feature flags...")
        seed_config()
        print("Sembrando catálogo de documentos KYC por rol (incluye merchant)...")
        seed_kyc()
        print("Sembrando catálogo de habilidades con rutas certificables...")
        seed_habilidades()

        db.session.commit()

        print("\n=== Seed completado ===")
        print(f"Seed completado: {len(created)} usuarios creados")
        if created:
            print("Emails creados:")
            for e in created:
                print(f"  - {e}")
        else:
            print("Ningún usuario nuevo (todos ya existían).")
