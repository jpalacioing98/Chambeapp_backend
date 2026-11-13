"""Siembra de simulacion completa para Valledupar.

Genera usuarios, negocios, solicitudes, ofertas, contratos, chambas, pagos,
KYC, portafolio, confianza, chat, notificaciones, tickets y demas modulos con
datos ficticios pero consistentes entre si.

Uso:
    python seed_simulacion_valledupar.py --reset
    python seed_simulacion_valledupar.py --reset --config app.config.TestingConfig --create-all
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable
from unicodedata import normalize

from sqlalchemy import func, text

from app import create_app
from app.extensions import bcrypt, db
from app.models import (
    AuditLog,
    AnuncioLaboral,
    AnuncioPostulacion,
    BadgeType,
    Chamba,
    Coin,
    Contract,
    Conversation,
    Dispute,
    DocumentoRequerido,
    DocumentoUsuario,
    EstadoAnuncio,
    EstadoChamba,
    EstadoContrato,
    EstadoHito,
    EstadoMarana,
    EstadoMaranaOferta,
    EstadoNegocio,
    EstadoOferta,
    EstadoPostulacionAnuncio,
    EstadoSolicitud,
    FeatureFlag,
    LegalAcceptance,
    Marana,
    MaranaOferta,
    Message,
    Milestone,
    Modalidad,
    Negocio,
    NegocioHorario,
    NegocioRating,
    NegocioReporte,
    Notification,
    Oferta,
    Profile,
    Rating,
    RolUsuario,
    Solicitud,
    Suscripcion,
    SystemConfig,
    Ticket,
    TipoModalidad,
    TipoMoneda,
    TipoNegocio,
    TipoTransaccion,
    Transaction,
    User,
    Verification,
    Wallet,
)
from app.models.badges import Badge
from app.models.cascade import NotificationCascade
from app.models.merchant import MerchantPaymentMethod, MerchantPreference
from app.models.payment import EstadoPago, Payment
from app.models.payment_method import MetodoPago
from app.models.portfolio import PortfolioItem
from app.models.recommendation_log import RecommendationLog
from app.models.region import Region
from app.models.trust import TrustScore
from app.data.seed_kyc import sync_kyc_catalog
from app.data.seed_regions import sync_regions
from app.services.avatar_seed import upload_seed_avatar

SIM_DOMAIN = "sim.chambeapp.co"
PASSWORD = "ChambeApp123!"
SEED = 20261029
NOW = datetime.utcnow().replace(microsecond=0)

CATEGORIAS = [
    "construccion",
    "electricidad",
    "plomeria",
    "carpinteria",
    "pintura",
    "limpieza",
    "jardineria",
    "transporte",
    "cocina",
    "tecnologia",
    "diseno",
    "cuidado_personas",
    "eventos",
    "otros",
]

CATEGORIA_PESOS = [18, 14, 13, 9, 8, 9, 6, 6, 5, 6, 4, 4, 3, 2]

PRECIOS = {
    "construccion": (70000, 450000),
    "electricidad": (60000, 350000),
    "plomeria": (50000, 300000),
    "carpinteria": (80000, 500000),
    "pintura": (40000, 250000),
    "limpieza": (30000, 200000),
    "jardineria": (40000, 250000),
    "transporte": (35000, 220000),
    "cocina": (50000, 260000),
    "tecnologia": (80000, 500000),
    "diseno": (60000, 400000),
    "cuidado_personas": (40000, 220000),
    "eventos": (90000, 600000),
    "otros": (50000, 300000),
}

BARRIOS = [
    ("Centro", 10.4631, -73.2536),
    ("El Caiguami", 10.4765, -73.2412),
    ("La Nevada", 10.4872, -73.2588),
    ("San Joaquin", 10.4518, -73.2384),
    ("Los Fundadores", 10.4925, -73.2681),
    ("La Esperanza", 10.4422, -73.2663),
    ("Villa Castro", 10.5004, -73.2337),
    ("Nicolas de Federman", 10.4719, -73.2804),
    ("El Carmen", 10.4556, -73.2711),
    ("La Victoria", 10.4838, -73.2265),
    ("San Martin", 10.4387, -73.2512),
    ("Nueva Granada", 10.5082, -73.2797),
    ("Primero de Mayo", 10.4469, -73.2871),
    ("Simon Bolivar", 10.4963, -73.2478),
    ("La Pedregosa", 10.4645, -73.2119),
    ("Los Milagros", 10.4321, -73.2294),
    ("La Ceiba", 10.5124, -73.2416),
    ("El Prado", 10.4788, -73.2923),
]

NOMBRES = [
    "Carlos", "Luis", "Jose", "Miguel", "Andres", "Jorge", "Pedro", "Juan",
    "Diego", "Fernando", "Rafael", "Wilson", "Oscar", "Alberto", "Camilo",
    "Maria", "Ana", "Laura", "Sandra", "Paula", "Carolina", "Diana", "Luz",
    "Martha", "Claudia", "Angela", "Yuliana", "Natalia", "Rosa", "Elena",
    "Jhon", "Brayan", "Kevin", "Fabian", "Nelson", "Hernan", "Ivan", "Mario",
]

APELLIDOS = [
    "Garcia", "Martinez", "Rodriguez", "Lopez", "Gonzalez", "Perez", "Diaz",
    "Torres", "Ramirez", "Vargas", "Castro", "Rojas", "Moreno", "Jimenez",
    "Herrera", "Medina", "Ospina", "Mejia", "Ariza", "Daza", "Gutierrez",
    "Mendoza", "Navarro", "Pineda", "Quintero", "Rincon", "Suarez", "Uribe",
]

CATEGORIA_ESPECIALIDADES = {
    "construccion": ["albanileria", "enchapes", "cimentacion", "revoque"],
    "electricidad": ["instalaciones", "tableros", "iluminacion", "mantenimiento"],
    "plomeria": ["tuberias", "fugas", "sanitarios", "calentadores"],
    "carpinteria": ["muebles", "puertas", "closets", "reparaciones"],
    "pintura": ["interiores", "exteriores", "impermeabilizacion", "acabados"],
    "limpieza": ["hogar", "oficinas", "profunda", "post-obra"],
    "jardineria": ["poda", "siembra", "mantenimiento", "riego"],
    "transporte": ["mudanzas", "carga", "domicilios", "traslados"],
    "cocina": ["almuerzos", "eventos", "reposteria", "catering"],
    "tecnologia": ["computadores", "redes", "celulares", "soporte"],
    "diseno": ["grafico", "web", "interiores", "publicidad"],
    "cuidado_personas": ["ninos", "adultos mayores", "acompanamiento", "enfermeria"],
    "eventos": ["decoracion", "sonido", "logistica", "mesas"],
    "otros": ["mandados", "auxiliares", "apoyo", "servicios"],
}

ESPECIFICACIONES = {
    "construccion": ["Nivelar superficie", "Retirar escombros", "Material incluido", "Trabajo en altura"],
    "electricidad": ["Breaker independiente", "Cable calibre 12", "Certificado RETIE", "Revision de tablero"],
    "plomeria": ["Tuberia PVC", "Deteccion de fuga", "Cambio de griferia", "Prueba de presion"],
    "carpinteria": ["Madera certificada", "Medidas exactas", "Acabado mate", "Instalacion incluida"],
    "pintura": ["Pintura tipo 2", "Dos manos", "Proteccion de muebles", "Resane incluido"],
    "limpieza": ["Productos incluidos", "Trabajo por horas", "Zonas comunes", "Finalizar mismo dia"],
    "jardineria": ["Poda de arboles", "Retiro de residuos", "Riego incluido", "Mantenimiento mensual"],
    "transporte": ["Vehiculo propio", "Ayudante incluido", "Carga asegurada", "Ruta fija"],
    "cocina": ["Ingredientes incluidos", "Menu acordado", "Servicio a domicilio", "Personal de apoyo"],
    "tecnologia": ["Diagnostico incluido", "Repuesto original", "Garantia 30 dias", "Soporte remoto"],
    "diseno": ["Briefing previo", "Dos propuestas", "Entrega digital", "Revision incluida"],
    "cuidado_personas": ["Experiencia certificada", "Turno diurno", "Referencias", "Primeros auxilios"],
    "eventos": ["Montaje y desmontaje", "Sonido profesional", "Decoracion tematica", "Coordinacion"],
    "otros": ["Precio a convenir", "Disponibilidad inmediata", "Trabajo puntual", "Apoyo general"],
}

TITULOS_SOLICITUD = [
    "Necesito {servicio} en {zona}",
    "Busco profesional para {servicio}",
    "{servicio} urgente en {zona}",
    "Servicio de {servicio} para el hogar",
    "Cotizacion para {servicio}",
    "Trabajo de {servicio} esta semana",
]

DESCRIPCIONES = [
    "Se requiere un profesional con experiencia para realizar el trabajo en las condiciones acordadas.",
    "El servicio debe incluir herramientas y materiales basicos; se coordina por chat la fecha exacta.",
    "Es para un inmueble familiar en Valledupar. Se espera puntualidad, buen trato y evidencia del trabajo.",
    "La persona interesada debe enviar su oferta con el valor final y el tiempo estimado de ejecucion.",
]

MENSAJES_OFERTA = [
    "Puedo realizar el trabajo esta semana. Incluyo herramientas y garantia.",
    "Tengo experiencia en la categoria y disponibilidad inmediata en la zona.",
    "Mi propuesta incluye materiales y mano de obra. Podemos ajustar el horario.",
    "He trabajado en solicitudes similares; puedo enviar referencias y fotos.",
]

COMENTARIOS_RATING = [
    "Excelente trabajo, puntual y muy profesional.",
    "Cumplio con lo acordado y dejo todo limpio.",
    "Buen trato y comunicacion durante el servicio.",
    "El trabajo quedo bien, aunque tardo un poco mas de lo previsto.",
    "Muy recomendado, volveria a contratar.",
    "Atendio la solicitud con responsabilidad.",
]

COMENTARIOS_NEGOCIO = [
    "Atencion rapida y precios justos.",
    "Buen surtido y personal amable.",
    "El servicio cumplio con lo esperado.",
    "Recomendado para compras del hogar.",
]

BANCOS = ["Nequi", "Daviplata", "Bancolombia", "Davivienda", "BBVA", "Banco Agrario"]

NEGOCIOS_SPEC = [
    ("Ferreteria El Cesar", "comercio", "construccion", "Centro"),
    ("Electricidad Vallenata", "servicio", "electricidad", "El Caiguami"),
    ("Plomeria La Guajira", "servicio", "plomeria", "La Nevada"),
    ("Pinturas del Valle", "hibrido", "pintura", "San Joaquin"),
    ("Maderas y Disenos", "comercio", "carpinteria", "Los Fundadores"),
    ("Limpieza Caribe", "servicio", "limpieza", "La Esperanza"),
    ("Jardines de la Sierra", "servicio", "jardineria", "Villa Castro"),
    ("Transportes Guatapuri", "servicio", "transporte", "Nicolas de Federman"),
    ("Cocina Costena", "hibrido", "cocina", "El Carmen"),
    ("TecnoValledupar", "comercio", "tecnologia", "La Victoria"),
    ("Eventos La Pedregosa", "servicio", "eventos", "La Pedregosa"),
    ("Cuidado y Bienestar", "servicio", "cuidado_personas", "Los Milagros"),
]

BADGE_CYCLE = [
    BadgeType.PRIMER_CONTRATO,
    BadgeType.PERFIL_COMPLETO,
    BadgeType.VERIFICADO,
    BadgeType.TOP_RATED,
    BadgeType.DIEZ_CONTRATOS,
    BadgeType.SIN_DISPUTAS,
]


@dataclass(frozen=True)
class Sizes:
    pds: int
    solicitantes: int
    merchants: int
    staff: int
    negocios: int
    solicitudes: int
    ofertas: int
    completadas: int
    en_progreso: int
    asignadas: int
    publicadas: int
    canceladas: int
    ocultas: int
    rechazadas: int
    borradores: int
    completado_pendiente: int
    pendiente: int
    cancelado: int
    marcado: int
    kyc_pds: int
    kyc_solicitantes: int
    transactions: int
    coins: int
    metros_pago: int
    reco_logs: int
    notifications: int
    conversations: int
    tickets: int
    disputes: int
    cascades: int
    anuncios: int
    postulaciones: int
    audit: int


def scaled_count(base: int, scale: float, minimum: int = 0) -> int:
    return max(minimum, int(round(base * scale)))


def build_sizes(scale: float) -> Sizes:
    pds = scaled_count(150, scale, 4)
    solicitantes = scaled_count(72, scale, 4)
    merchants = scaled_count(10, scale, 2)
    staff = scaled_count(8, scale, 4)
    solicitudes = scaled_count(300, scale, 8)

    completadas = scaled_count(100, scale, 2)
    en_progreso = scaled_count(50, scale, 1)
    asignadas = scaled_count(35, scale, 1)
    publicadas = scaled_count(80, scale, 1)
    canceladas = scaled_count(20, scale, 1)
    ocultas = scaled_count(5, scale, 1)
    rechazadas = scaled_count(5, scale, 1)
    borradores = scaled_count(5, scale, 1)
    total = completadas + en_progreso + asignadas + publicadas + canceladas + ocultas + rechazadas + borradores
    publicadas += solicitudes - total
    if publicadas < 0:
        raise SystemExit("Perfil de solicitudes invalido para la escala indicada")

    return Sizes(
        pds=pds,
        solicitantes=solicitantes,
        merchants=merchants,
        staff=staff,
        negocios=scaled_count(12, scale, 2),
        solicitudes=solicitudes,
        ofertas=scaled_count(720, scale, 12),
        completadas=completadas,
        en_progreso=en_progreso,
        asignadas=asignadas,
        publicadas=publicadas,
        canceladas=canceladas,
        ocultas=ocultas,
        rechazadas=rechazadas,
        borradores=borradores,
        completado_pendiente=scaled_count(15, scale, 1),
        pendiente=scaled_count(10, scale, 1),
        cancelado=scaled_count(7, scale, 1),
        marcado=scaled_count(3, scale, 1),
        kyc_pds=scaled_count(80, scale, 2),
        kyc_solicitantes=scaled_count(20, scale, 2),
        transactions=scaled_count(700, scale, 40),
        coins=scaled_count(500, scale, 30),
        metros_pago=scaled_count(320, scale, 12),
        reco_logs=scaled_count(2000, scale, 80),
        notifications=scaled_count(1800, scale, 80),
        conversations=scaled_count(150, scale, 8),
        tickets=scaled_count(30, scale, 3),
        disputes=scaled_count(15, scale, 2),
        cascades=scaled_count(80, scale, 4),
        anuncios=scaled_count(15, scale, 2),
        postulaciones=scaled_count(50, scale, 4),
        audit=scaled_count(250, scale, 10),
    )


def slugify(value: str) -> str:
    raw = normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    cleaned = "".join(c.lower() if c.isalnum() else "-" for c in raw)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-")[:165]


def geom_value(lat: float, lng: float) -> str:
    return f"SRID=4326;POINT({lng:.6f} {lat:.6f})"


def jitter(rng: random.Random, lat: float, lng: float, max_km: float = 1.2) -> tuple[float, float]:
    angle = rng.uniform(0, math.tau)
    distance = rng.uniform(0, max_km)
    dlat = (distance * math.cos(angle)) / 111.0
    dlng = (distance * math.sin(angle)) / (111.0 * math.cos(math.radians(lat)))
    return round(lat + dlat, 6), round(lng + dlng, 6)


def far_point(rng: random.Random, lat: float, lng: float) -> tuple[float, float]:
    angle = rng.uniform(0, math.tau)
    distance = rng.uniform(5.0, 14.0)
    dlat = (distance * math.cos(angle)) / 111.0
    dlng = (distance * math.sin(angle)) / (111.0 * math.cos(math.radians(lat)))
    return round(lat + dlat, 6), round(lng + dlng, 6)


def random_dt(rng: random.Random, start: datetime, end: datetime) -> datetime:
    if end <= start:
        return start.replace(microsecond=0)
    seconds = int((end - start).total_seconds())
    return (start + timedelta(seconds=rng.randint(0, max(0, seconds)))).replace(microsecond=0)


def clamp_dt(value: datetime, end: datetime) -> datetime:
    return min(value, end).replace(microsecond=0)


def person_name(rng: random.Random) -> str:
    return f"{rng.choice(NOMBRES)} {rng.choice(APELLIDOS)} {rng.choice(APELLIDOS)}"


def phone(rng: random.Random) -> str:
    return f"3{rng.choice(['00', '01', '02', '04', '05', '10', '11', '12', '13', '14', '15', '16', '17', '18', '20', '21', '22', '23'])}{rng.randint(1000000, 9999999)}"


def category_weights(rng: random.Random) -> str:
    return rng.choices(CATEGORIAS, weights=CATEGORIA_PESOS, k=1)[0]


def simulate_price(rng: random.Random, categoria: str) -> int:
    low, high = PRECIOS.get(categoria, PRECIOS["otros"])
    value = rng.randint(low, high)
    return max(20000, int(round(value / 5000.0) * 5000))


def fake_email(role: str, index: int) -> str:
    return f"{role}{index:03d}@{SIM_DOMAIN}"


def fake_username(role: str, index: int) -> str:
    return f"{role}{index:03d}"


def add_all_batched(items: Iterable[Any], batch_size: int = 500) -> None:
    batch: list[Any] = []
    for item in items:
        batch.append(item)
        if len(batch) >= batch_size:
            db.session.add_all(batch)
            db.session.flush()
            batch = []
    if batch:
        db.session.add_all(batch)
        db.session.flush()


def sim_user_ids() -> list[int]:
    return [
        row[0]
        for row in db.session.query(User.id)
        .filter(User.email.like(f"%@{SIM_DOMAIN}"))
        .all()
    ]


def reset_simulation() -> None:
    ids = sim_user_ids()
    if not ids:
        print("Reset: no hay datos de simulacion previos.")
        return

    solicitud_ids = [
        row[0]
        for row in db.session.query(Solicitud.id)
        .filter(Solicitud.solicitante_id.in_(ids))
        .all()
    ]
    contract_ids = [
        row[0]
        for row in db.session.query(Contract.id)
        .filter(
            (Contract.solicitante_id.in_(ids)) | (Contract.proveedor_id.in_(ids))
        )
        .all()
    ]
    chamba_ids = [
        row[0]
        for row in db.session.query(Chamba.id)
        .filter(Chamba.contract_id.in_(contract_ids))
        .all()
    ]
    marana_ids = [
        row[0]
        for row in db.session.query(Marana.id)
        .filter(Marana.solicitante_id.in_(ids))
        .all()
    ]
    negocio_ids = [
        row[0]
        for row in db.session.query(Negocio.id)
        .filter(Negocio.owner_id.in_(ids))
        .all()
    ]

    if marana_ids:
        db.session.query(MaranaOferta).filter(
            MaranaOferta.marana_id.in_(marana_ids)
        ).delete(synchronize_session=False)
        db.session.query(Marana).filter(Marana.id.in_(marana_ids)).delete(
            synchronize_session=False
        )
    if chamba_ids:
        db.session.query(Chamba).filter(Chamba.id.in_(chamba_ids)).delete(
            synchronize_session=False
        )
    if contract_ids:
        db.session.query(Milestone).filter(
            Milestone.contract_id.in_(contract_ids)
        ).delete(synchronize_session=False)
        db.session.query(Payment).filter(
            Payment.contract_id.in_(contract_ids)
        ).delete(synchronize_session=False)
        db.session.query(Dispute).filter(
            Dispute.contract_id.in_(contract_ids)
        ).delete(synchronize_session=False)
        db.session.query(Contract).filter(Contract.id.in_(contract_ids)).delete(
            synchronize_session=False
        )
    if solicitud_ids:
        db.session.query(Oferta).filter(
            Oferta.solicitud_id.in_(solicitud_ids)
        ).delete(synchronize_session=False)
        db.session.query(Rating).filter(
            Rating.service_id.in_(solicitud_ids)
        ).delete(synchronize_session=False)
        db.session.query(Modalidad).filter(
            Modalidad.service_id.in_(solicitud_ids)
        ).delete(synchronize_session=False)
        db.session.query(NotificationCascade).filter(
            NotificationCascade.solicitud_id.in_(solicitud_ids)
        ).delete(synchronize_session=False)
        db.session.query(RecommendationLog).filter(
            RecommendationLog.solicitud_id.in_(solicitud_ids)
        ).delete(synchronize_session=False)
        db.session.query(Solicitud).filter(Solicitud.id.in_(solicitud_ids)).delete(
            synchronize_session=False
        )
    anuncio_ids = [
        row[0]
        for row in db.session.query(AnuncioLaboral.id)
        .filter(
            (AnuncioLaboral.negocio_id.in_(negocio_ids))
            | (AnuncioLaboral.negocio_id.in_(ids))
        )
        .all()
    ]
    if anuncio_ids:
        db.session.query(AnuncioPostulacion).filter(
            AnuncioPostulacion.anuncio_id.in_(anuncio_ids)
        ).delete(synchronize_session=False)
        db.session.query(AnuncioLaboral).filter(
            AnuncioLaboral.id.in_(anuncio_ids)
        ).delete(synchronize_session=False)

    if negocio_ids:
        db.session.query(NegocioReporte).filter(
            NegocioReporte.negocio_id.in_(negocio_ids)
        ).delete(synchronize_session=False)
        db.session.query(NegocioRating).filter(
            NegocioRating.negocio_id.in_(negocio_ids)
        ).delete(synchronize_session=False)
        db.session.query(NegocioHorario).filter(
            NegocioHorario.negocio_id.in_(negocio_ids)
        ).delete(synchronize_session=False)
        db.session.query(Negocio).filter(Negocio.id.in_(negocio_ids)).delete(
            synchronize_session=False
        )

    conversation_ids = [
        row[0]
        for row in db.session.query(Conversation.id)
        .filter(
            (Conversation.user_a_id.in_(ids)) | (Conversation.user_b_id.in_(ids))
        )
        .all()
    ]
    if conversation_ids:
        db.session.query(Message).filter(
            Message.conversation_id.in_(conversation_ids)
        ).delete(synchronize_session=False)
        db.session.query(Conversation).filter(
            Conversation.id.in_(conversation_ids)
        ).delete(synchronize_session=False)

    db.session.query(Ticket).filter(Ticket.user_id.in_(ids)).delete(
        synchronize_session=False
    )
    db.session.query(Notification).filter(Notification.user_id.in_(ids)).delete(
        synchronize_session=False
    )
    db.session.query(Coin).filter(Coin.user_id.in_(ids)).delete(
        synchronize_session=False
    )
    db.session.query(Transaction).filter(
        Transaction.wallet_id.in_(
            db.session.query(Wallet.id).filter(Wallet.user_id.in_(ids))
        )
    ).delete(synchronize_session=False)
    db.session.query(Wallet).filter(Wallet.user_id.in_(ids)).delete(
        synchronize_session=False
    )
    db.session.query(MetodoPago).filter(MetodoPago.user_id.in_(ids)).delete(
        synchronize_session=False
    )
    db.session.query(MerchantPaymentMethod).filter(
        MerchantPaymentMethod.user_id.in_(ids)
    ).delete(synchronize_session=False)
    db.session.query(MerchantPreference).filter(
        MerchantPreference.user_id.in_(ids)
    ).delete(synchronize_session=False)
    db.session.query(Suscripcion).filter(Suscripcion.user_id.in_(ids)).delete(
        synchronize_session=False
    )
    db.session.query(DocumentoUsuario).filter(
        DocumentoUsuario.user_id.in_(ids)
    ).delete(synchronize_session=False)
    db.session.query(PortfolioItem).filter(
        PortfolioItem.pds_id.in_(ids)
    ).delete(synchronize_session=False)
    db.session.query(Badge).filter(Badge.usuario_id.in_(ids)).delete(
        synchronize_session=False
    )
    db.session.query(TrustScore).filter(TrustScore.pds_id.in_(ids)).delete(
        synchronize_session=False
    )
    db.session.query(Verification).filter(Verification.user_id.in_(ids)).delete(
        synchronize_session=False
    )
    db.session.query(LegalAcceptance).filter(
        LegalAcceptance.user_id.in_(ids)
    ).delete(synchronize_session=False)
    db.session.query(Profile).filter(Profile.user_id.in_(ids)).delete(
        synchronize_session=False
    )
    db.session.query(AuditLog).filter(AuditLog.actor_id.in_(ids)).delete(
        synchronize_session=False
    )
    db.session.query(User).filter(User.id.in_(ids)).delete(synchronize_session=False)

    db.session.commit()
    print(f"Reset: eliminados {len(ids)} usuarios de simulacion y sus dependencias.")


def ensure_schema_and_catalogs(create_all: bool) -> None:
    dialect = db.engine.dialect.name
    if create_all:
        if dialect == "postgresql":
            db.session.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            db.session.commit()
        db.create_all()
        print("Esquema creado/verificado.")

    sync_kyc_catalog()
    sync_regions()
    print("Catalogos KYC y regiones sincronizados.")


def ensure_sim_isolation(reset: bool) -> None:
    existing = db.session.query(User.id).filter(
        User.email.like(f"%@{SIM_DOMAIN}")
    ).first()
    if existing and not reset:
        raise SystemExit(
            "Ya existen datos de simulacion. Use --reset para reemplazarlos."
        )


def upsert_config(key: str, value: Any, description: str | None = None) -> None:
    SystemConfig.set_value(key, value, description=description, commit=False)


def ensure_flags() -> None:
    flags = {
        "cobertura_valledupar": True,
        "ml_ranking_activo": True,
        "cascadas_activas": True,
        "pagos_simulados": True,
    }
    for key, enabled in flags.items():
        row = FeatureFlag.query.filter_by(key=key).first()
        if row is None:
            db.session.add(
                FeatureFlag(
                    key=key,
                    enabled=enabled,
                    description=f"Flag de simulacion {key}",
                )
            )
        else:
            row.enabled = enabled


def create_staff_roles(count: int) -> list[str]:
    base = ["superadmin", "admin", "admin", "verificador", "verificador", "verificador", "soporte", "soporte"]
    if count <= len(base):
        return base[:count]
    return base + ["soporte"] * (count - len(base))


def create_users(rng: random.Random, sizes: Sizes) -> dict[str, list[User]]:
    password_hash = bcrypt.generate_password_hash(PASSWORD).decode("utf-8")
    region = Region.query.filter_by(clave="caribe").first()
    region_id = region.id if region else None
    used_usernames = {
        row[0] for row in db.session.query(User.username).filter(User.username.isnot(None)).all()
    }

    def unique_username(base: str) -> str:
        candidate = base
        suffix = 0
        while candidate in used_usernames:
            suffix += 1
            candidate = f"{base}_{suffix}"
        used_usernames.add(candidate)
        return candidate

    pds_users: list[User] = []
    solicitantes: list[User] = []
    merchants: list[User] = []
    staff: list[User] = []

    # Contador global para que cada usuario reciba una cara distinta de
    # i.pravatar.cc (el índice por rol se reinicia en cada grupo).
    avatar_counter = 0

    def add_user(
        role: RolUsuario,
        index: int,
        email: str,
        username: str,
        name: str,
        registered_days: int,
        zona: str,
        lat: float,
        lng: float,
        status: str = "active",
    ) -> User:
        nonlocal avatar_counter
        avatar_counter += 1
        registered_at = clamp_dt(NOW - timedelta(days=registered_days), NOW)
        last_login = clamp_dt(
            NOW - timedelta(days=rng.randint(0, 25), hours=rng.randint(0, 23)),
            NOW,
        )
        if last_login < registered_at:
            last_login = registered_at
        user = User(
            email=email,
            password_hash=password_hash,
            rol=role,
            status=status,
            nombre=name,
            username=unique_username(username),
            telefono=phone(rng),
            edad_verificada=True,
            acepto_tyc=True,
            consentimiento_datos=True,
            email_verificado=True,
            fecha_registro=registered_at,
            last_login=last_login,
            activo=status == "active",
            two_factor_enabled=(index % 9 == 0) if role in (RolUsuario.PDS, RolUsuario.SOLICITANTE) else role in (RolUsuario.ADMIN, RolUsuario.SUPERADMIN),
            region_id=None if role == RolUsuario.SUPERADMIN else region_id,
        )
        profile = Profile(
            user=user,
            habilidades=[],
            experiencia="",
            zona=zona,
            calificacion_promedio=0.0,
            verificado=False,
            badges=[],
            portafolio=[],
            categorias=[],
            perfil_completo=False,
            foto_perfil=upload_seed_avatar(
                f"sim/{role.value}/{index:03d}", avatar_counter
            ),
            latitud=lat,
            longitud=lng,
            geom=geom_value(lat, lng),
            plan="free",
            destacado=False,
            onboarding_completed=False,
            onboarding_step=0,
        )
        user.profile = profile
        db.session.add(user)
        return user

    for i in range(1, sizes.pds + 1):
        zona, base_lat, base_lng = rng.choice(BARRIOS)
        if i % 10 == 0:
            lat, lng = far_point(rng, base_lat, base_lng)
        else:
            lat, lng = jitter(rng, base_lat, base_lng, 1.4)
        primary = category_weights(rng)
        secondary = rng.sample([c for c in CATEGORIAS if c != primary], k=min(2, len(CATEGORIAS) - 1))
        cats = [primary] + secondary
        plan = rng.choices(["free", "basico", "profesional"], weights=[55, 30, 15], k=1)[0]
        status = "active" if i <= max(1, sizes.pds - 8) else ("suspended" if i % 2 else "banned")
        user = add_user(
            RolUsuario.PDS,
            i,
            fake_email("pds", i),
            fake_username("pds", i),
            person_name(rng),
            rng.randint(10, 360),
            zona,
            lat,
            lng,
            status,
        )
        profile = user.profile
        profile.habilidades = cats + [rng.choice(CATEGORIA_ESPECIALIDADES[primary])]
        profile.categorias = cats
        profile.experiencia = f"{rng.randint(1, 15)} anos de experiencia en {primary} y oficios relacionados."
        profile.verificado = i <= sizes.kyc_pds and i <= 68
        profile.badges = [b.value for b in rng.sample(BADGE_CYCLE, k=min(2, len(BADGE_CYCLE)))]
        profile.portafolio = [f"https://{SIM_DOMAIN}/portfolio/pds{i:03d}/{j}.jpg" for j in range(1, rng.randint(2, 4))]
        profile.perfil_completo = i % 10 != 0
        profile.plan = plan
        profile.destacado = i % 7 == 0
        profile.onboarding_completed = i % 10 != 0
        profile.onboarding_step = 5 if profile.onboarding_completed else rng.randint(1, 4)
        pds_users.append(user)

    for i in range(1, sizes.solicitantes + 1):
        zona, base_lat, base_lng = rng.choice(BARRIOS)
        lat, lng = jitter(rng, base_lat, base_lng, 2.0) if i % 11 else far_point(rng, base_lat, base_lng)
        primary = category_weights(rng)
        status = "active" if i <= max(1, sizes.solicitantes - 3) else "suspended"
        user = add_user(
            RolUsuario.SOLICITANTE,
            i,
            fake_email("sol", i),
            fake_username("sol", i),
            person_name(rng),
            rng.randint(5, 350),
            zona,
            lat,
            lng,
            status,
        )
        profile = user.profile
        profile.categorias = [primary]
        profile.habilidades = [rng.choice(CATEGORIA_ESPECIALIDADES[primary])]
        profile.experiencia = "Solicitante de servicios para el hogar y pequenos negocios."
        profile.verificado = False
        profile.plan = rng.choices(["free", "basico"], weights=[75, 25], k=1)[0]
        profile.perfil_completo = i % 8 != 0
        profile.onboarding_completed = i % 8 != 0
        profile.onboarding_step = 5 if profile.onboarding_completed else rng.randint(1, 4)
        solicitantes.append(user)

    for i in range(1, sizes.merchants + 1):
        zona, base_lat, base_lng = rng.choice(BARRIOS)
        lat, lng = jitter(rng, base_lat, base_lng, 1.0)
        user = add_user(
            RolUsuario.MERCHANT,
            i,
            fake_email("neg", i),
            fake_username("neg", i),
            person_name(rng),
            rng.randint(30, 340),
            zona,
            lat,
            lng,
            "active",
        )
        profile = user.profile
        profile.categorias = [NEGOCIOS_SPEC[(i - 1) % len(NEGOCIOS_SPEC)][2]]
        profile.habilidades = ["administracion", "atencion al cliente"]
        profile.experiencia = "Comerciante con establecimiento en Valledupar."
        profile.verificado = True
        profile.plan = "profesional"
        profile.perfil_completo = True
        profile.onboarding_completed = True
        profile.onboarding_step = 5
        profile.destacado = i % 4 == 0
        merchants.append(user)

    roles = create_staff_roles(sizes.staff)
    for i, role_name in enumerate(roles, start=1):
        role = RolUsuario(role_name)
        zona, base_lat, base_lng = rng.choice(BARRIOS[:6])
        lat, lng = jitter(rng, base_lat, base_lng, 0.8)
        email = f"staff.{role_name}{i:02d}@{SIM_DOMAIN}"
        user = add_user(
            role,
            i,
            email,
            f"staff_{role_name}{i:02d}",
            person_name(rng),
            rng.randint(120, 500),
            zona,
            lat,
            lng,
            "active",
        )
        profile = user.profile
        profile.categorias = ["otros"]
        profile.habilidades = ["moderacion", "soporte", "verificacion"]
        profile.experiencia = "Equipo interno de operaciones de ChambeApp."
        profile.verificado = True
        profile.plan = "profesional"
        profile.perfil_completo = True
        profile.onboarding_completed = True
        profile.onboarding_step = 5
        staff.append(user)

    db.session.flush()

    acceptances = [
        LegalAcceptance(
            user_id=u.id,
            version_tyc="2026-01",
            fecha=u.fecha_registro,
            ip=f"190.0.{rng.randint(1, 250)}.{rng.randint(1, 250)}",
        )
        for u in pds_users + solicitantes + merchants + staff
    ]
    add_all_batched(acceptances, 400)
    db.session.commit()
    print(
        f"Usuarios: {len(pds_users)} pds, {len(solicitantes)} solicitantes, "
        f"{len(merchants)} merchants, {len(staff)} staff."
    )
    return {
        "pds": pds_users,
        "solicitantes": solicitantes,
        "merchants": merchants,
        "staff": staff,
    }


def create_subscriptions(rng: random.Random, users: dict[str, list[User]]) -> list[Suscripcion]:
    rows: list[Suscripcion] = []
    targets = users["pds"] + users["solicitantes"][:20]
    for user in targets:
        plan = user.profile.plan if user.profile.plan in ("free", "basico", "profesional") else "free"
        amount = {"free": 0, "basico": 19900, "profesional": 49900}[plan]
        active = rng.random() < 0.88
        start = clamp_dt(NOW - timedelta(days=rng.randint(30, 300)), NOW)
        row = Suscripcion(
            user_id=user.id,
            plan=plan,
            estado="activa" if active else "vencida",
            inicio_en=start,
            fin_en=NOW + timedelta(days=30) if active else NOW - timedelta(days=rng.randint(1, 15)),
            monto=amount,
            metodo_pago="mock",
            creado_en=start,
            actualizado_en=start,
        )
        rows.append(row)
    add_all_batched(rows, 200)
    db.session.commit()
    print(f"Suscripciones: {len(rows)}")
    return rows


def create_businesses(rng: random.Random, users: dict[str, list[User]], sizes: Sizes) -> list[Negocio]:
    merchants = users["merchants"]
    rows: list[Negocio] = []
    for i, (name, tipo, categoria, barrio) in enumerate(NEGOCIOS_SPEC[: sizes.negocios], start=1):
        base_lat, base_lng = next((lat, lng) for b, lat, lng in BARRIOS if b == barrio)
        lat, lng = jitter(rng, base_lat, base_lng, 1.0)
        estado = (
            EstadoNegocio.ACTIVO.value
            if i <= 9
            else (EstadoNegocio.PENDIENTE_VERIFICACION.value if i <= 11 else EstadoNegocio.SUSPENDIDO.value)
        )
        row = Negocio(
            owner_id=merchants[(i - 1) % len(merchants)].id,
            nombre=name,
            slug=slugify(f"{name}-valledupar-{i}"),
            descripcion=f"{name} presta servicios de {categoria} en Valledupar y el area metropolitana.",
            tipo=tipo,
            logo_url=f"https://{SIM_DOMAIN}/negocios/{i}/logo.png",
            banner_url=f"https://{SIM_DOMAIN}/negocios/{i}/banner.jpg",
            imagenes=[f"https://{SIM_DOMAIN}/negocios/{i}/{j}.jpg" for j in range(1, 4)],
            latitud=lat,
            longitud=lng,
            direccion=f"Carrera {rng.randint(4, 30)} #{rng.randint(1, 40)}-{rng.randint(1, 90)}, {barrio}",
            ciudad="Valledupar",
            departamento="Cesar",
            radio_cobertura_km=rng.choice([3.0, 5.0, 8.0, 12.0]),
            geom=geom_value(lat, lng),
            categoria_principal=categoria,
            categorias_secundarias=rng.sample(
                [c for c in CATEGORIAS if c != categoria], k=2
            ),
            servicios=[
                {
                    "nombre": f"{categoria.title()} basico",
                    "descripcion": "Servicio basico con visita y cotizacion.",
                    "precio_desde": simulate_price(rng, categoria),
                },
                {
                    "nombre": f"{categoria.title()} integral",
                    "descripcion": "Servicio completo con materiales y garantia.",
                    "precio_desde": simulate_price(rng, categoria),
                },
            ],
            palabras_clave=[categoria, barrio.lower(), "valledupar", "cesar"],
            whatsapp=phone(rng),
            whatsapp_mensaje_pre=f"Hola, vi {name} en ChambeApp y quiero cotizar.",
            instagram=f"https://instagram.com/{slugify(name)}",
            facebook=f"https://facebook.com/{slugify(name)}",
            tiktok=None,
            sitio_web=f"https://{slugify(name)}.sim.chambeapp.co",
            calificacion_promedio=0.0,
            total_calificaciones=0,
            verificado=estado == EstadoNegocio.ACTIVO.value,
            estado=estado,
            motivo_rechazo=None,
            creado_en=clamp_dt(NOW - timedelta(days=rng.randint(60, 320)), NOW),
            actualizado_en=clamp_dt(NOW - timedelta(days=rng.randint(0, 20)), NOW),
        )
        db.session.add(row)
        rows.append(row)
    db.session.flush()

    for row in rows:
        for day in range(7):
            closed = day == 6 and row.id % 3 == 0
            db.session.add(
                NegocioHorario(
                    negocio_id=row.id,
                    dia_semana=day,
                    abierto=not closed,
                    hora_apertura=None if closed else time(8, 0),
                    hora_cierre=None if closed else time(18, 0),
                )
            )

    prefs: list[MerchantPreference] = []
    for merchant in merchants:
        prefs.append(
            MerchantPreference(
                user_id=merchant.id,
                notif_nueva_solicitud=True,
                notif_nueva_resena=True,
                notif_estado_kyc=True,
                notif_pago_recibido=True,
                push_enabled=True,
                email_digest=rng.choice(["daily", "weekly", "off"]),
                idioma="es",
                tema=rng.choice(["system", "light", "dark"]),
            )
        )
    add_all_batched(prefs, 50)

    merchant_methods: list[MerchantPaymentMethod] = []
    for merchant in merchants:
        for j in range(rng.randint(1, 2)):
            merchant_methods.append(
                MerchantPaymentMethod(
                    user_id=merchant.id,
                    tipo=rng.choice(["nequi", "bancolombia", "daviplata", "efectivo"]),
                    detalle={
                        "numero": phone(rng),
                        "titular": merchant.nombre,
                        "banco": rng.choice(BANCOS),
                    },
                    principal=j == 0,
                    activo=True,
                )
            )
    add_all_batched(merchant_methods, 50)
    db.session.commit()
    print(f"Negocios: {len(rows)}; preferencias: {len(prefs)}; metodos merchant: {len(merchant_methods)}")
    return rows


def create_financial_profiles(
    rng: random.Random, users: dict[str, list[User]], sizes: Sizes
) -> dict[str, Any]:
    all_users = users["pds"] + users["solicitantes"] + users["merchants"] + users["staff"]
    wallets: list[Wallet] = []
    for user in all_users:
        wallets.append(
            Wallet(
                user_id=user.id,
                saldo=0,
                saldo_bloqueado=0,
                created_at=clamp_dt(NOW - timedelta(days=rng.randint(1, 200)), NOW),
                updated_at=NOW,
            )
        )
    add_all_batched(wallets, 300)
    db.session.flush()

    methods: list[MetodoPago] = []
    for user in all_users:
        methods.append(
            MetodoPago(
                user_id=user.id,
                tipo="billetera",
                banco="ChambeApp",
                numero_cuenta=f"WALLET-{user.id:05d}",
                es_principal=True,
                creado_en=user.fecha_registro,
            )
        )
    bank_targets = rng.sample(all_users, k=min(len(all_users), max(10, sizes.metros_pago - len(all_users))))
    for user in bank_targets:
        methods.append(
            MetodoPago(
                user_id=user.id,
                tipo="banco",
                banco=rng.choice(BANCOS),
                numero_cuenta=phone(rng),
                es_principal=False,
                creado_en=clamp_dt(NOW - timedelta(days=rng.randint(1, 180)), NOW),
            )
        )
    add_all_batched(methods, 300)

    coins: list[Coin] = []
    for _ in range(sizes.coins):
        user = rng.choice(all_users)
        tipo = rng.choices(
            [TipoMoneda.COMPRADA, TipoMoneda.PROMOCIONAL, TipoMoneda.GANADA],
            weights=[35, 40, 25],
            k=1,
        )[0]
        coins.append(
            Coin(
                user_id=user.id,
                cantidad=rng.randint(1, 40),
                tipo=tipo,
                vence_en=NOW + timedelta(days=rng.randint(15, 180)) if tipo == TipoMoneda.PROMOCIONAL else None,
                created_at=clamp_dt(NOW - timedelta(days=rng.randint(0, 120)), NOW),
            )
        )
    add_all_batched(coins, 300)

    types = [
        TipoTransaccion.DEPOSITO,
        TipoTransaccion.COMISION,
        TipoTransaccion.RETIRO,
        TipoTransaccion.MONEDAS,
        TipoTransaccion.REEMBOLSO,
    ]
    transactions: list[Transaction] = []
    balances: dict[int, int] = {w.id: 0 for w in wallets}
    for i in range(sizes.transactions):
        wallet = rng.choice(wallets)
        tipo = types[i % len(types)]
        magnitude = rng.randrange(10000, 500000, 5000)
        if tipo in (TipoTransaccion.DEPOSITO, TipoTransaccion.REEMBOLSO):
            amount = magnitude
        elif tipo == TipoTransaccion.MONEDAS:
            amount = -rng.randrange(5000, 80000, 1000)
        else:
            amount = -magnitude
        balances[wallet.id] += amount
        transactions.append(
            Transaction(
                wallet_id=wallet.id,
                tipo=tipo,
                monto=amount,
                descripcion=f"Movimiento simulado {tipo.value}",
                referencia=f"SIM-TX-{i + 1:06d}",
                created_at=clamp_dt(NOW - timedelta(days=rng.randint(0, 180), hours=rng.randint(0, 23)), NOW),
            )
        )
    add_all_batched(transactions, 500)

    for wallet in wallets:
        wallet.saldo = max(10000, balances.get(wallet.id, 0) + rng.randint(20000, 150000))
        wallet.saldo_bloqueado = rng.choice([0, 0, 0, 5000, 10000, 25000])
        wallet.updated_at = NOW
    db.session.commit()
    print(
        f"Finanzas: {len(wallets)} wallets, {len(methods)} metodos, "
        f"{len(coins)} coins, {len(transactions)} transacciones."
    )
    return {"wallets": wallets, "methods": methods, "coins": coins, "transactions": transactions}


def create_solicitudes(
    rng: random.Random, users: dict[str, list[User]], sizes: Sizes
) -> list[dict[str, Any]]:
    states: list[EstadoSolicitud] = []
    states += [EstadoSolicitud.COMPLETADO] * sizes.completadas
    states += [EstadoSolicitud.EN_PROGRESO] * sizes.en_progreso
    states += [EstadoSolicitud.ASIGNADA] * sizes.asignadas
    states += [EstadoSolicitud.PUBLICADO] * sizes.publicadas
    states += [EstadoSolicitud.CANCELADO] * sizes.canceladas
    states += [EstadoSolicitud.OCULTO] * sizes.ocultas
    states += [EstadoSolicitud.RECHAZADO] * sizes.rechazadas
    states += [EstadoSolicitud.BORRADOR] * sizes.borradores
    rng.shuffle(states)

    age_ranges = {
        EstadoSolicitud.COMPLETADO: (35, 330),
        EstadoSolicitud.EN_PROGRESO: (6, 55),
        EstadoSolicitud.ASIGNADA: (2, 20),
        EstadoSolicitud.PUBLICADO: (0, 35),
        EstadoSolicitud.CANCELADO: (20, 180),
        EstadoSolicitud.OCULTO: (20, 100),
        EstadoSolicitud.RECHAZADO: (10, 100),
        EstadoSolicitud.BORRADOR: (0, 8),
    }

    result: list[dict[str, Any]] = []
    for i, state in enumerate(states, start=1):
        owner = rng.choice(users["solicitantes"])
        if rng.random() < 0.10:
            owner = rng.choice(users["merchants"])
        categoria = category_weights(rng)
        if owner.rol == RolUsuario.MERCHANT:
            categoria = owner.profile.categorias[0] if owner.profile.categorias else categoria
        zona, base_lat, base_lng = rng.choice(BARRIOS)
        if i % 10 == 0:
            lat, lng = far_point(rng, base_lat, base_lng)
        else:
            lat, lng = jitter(rng, base_lat, base_lng, 2.2)
        low, high = age_ranges[state]
        created = clamp_dt(NOW - timedelta(days=rng.randint(low, high), hours=rng.randint(0, 23)), NOW)
        desired = created.date() + timedelta(days=rng.randint(1, 20))
        presupuesto = simulate_price(rng, categoria) if rng.random() < 0.82 else None
        title = rng.choice(TITULOS_SOLICITUD).format(
            servicio=rng.choice(CATEGORIA_ESPECIALIDADES[categoria]),
            zona=zona,
        )
        descripcion = (
            f"{rng.choice(DESCRIPCIONES)} Categoria: {categoria}. "
            f"Zona: {zona}, Valledupar."
        )
        specs = rng.sample(
            ESPECIFICACIONES[categoria],
            k=min(len(ESPECIFICACIONES[categoria]), rng.randint(2, 4)),
        )
        row = Solicitud(
            solicitante_id=owner.id,
            titulo=title,
            categoria=categoria,
            descripcion=descripcion,
            ubicacion=zona,
            latitud=lat,
            longitud=lng,
            direccion=f"Calle {rng.randint(1, 45)} #{rng.randint(1, 35)}-{rng.randint(1, 80)}, {zona}",
            presupuesto=presupuesto,
            fecha_deseada=desired,
            urgencia=rng.choices(
                ["hoy", "semana", "flexible"], weights=[20, 55, 25], k=1
            )[0],
            estado=state,
            especificaciones_tecnicas=specs,
            imagen_360=f"https://{SIM_DOMAIN}/solicitudes/{i}/360.jpg" if rng.random() < 0.06 else None,
            horario=rng.choice(
                ["Manana (6:00 - 12:00)", "Tarde (12:00 - 18:00)", "Noche (18:00 - 21:00)", "Flexible"]
            ),
            imagenes=[f"https://{SIM_DOMAIN}/solicitudes/{i}/{j}.jpg" for j in range(1, rng.randint(1, 3))] if rng.random() < 0.45 else [],
            radio_km=rng.choice([2.0, 3.0, 5.0, 5.0, 8.0, 10.0, 15.0]),
            creado_en=created,
            actualizado_en=clamp_dt(created + timedelta(hours=rng.randint(1, 72)), NOW),
        )
        db.session.add(row)
        result.append(
            {
                "sol": row,
                "state": state,
                "owner": owner,
                "category": categoria,
                "created": created,
                "index": i,
            }
        )
    db.session.flush()
    db.session.commit()
    print(f"Solicitudes: {len(result)}")
    return result


def choose_provider(
    rng: random.Random,
    pds_users: list[User],
    categoria: str,
    excluded: set[int],
) -> User:
    candidates = [u for u in pds_users if u.id not in excluded and u.status == "active"]
    if not candidates:
        candidates = [u for u in pds_users if u.id not in excluded]
    if not candidates:
        candidates = pds_users
    weights = []
    for user in candidates:
        cats = list((user.profile.categorias or []) + (user.profile.habilidades or []))
        weights.append(5 if categoria in cats else 1)
    return rng.choices(candidates, weights=weights, k=1)[0]


def offer_amount(rng: random.Random, sol: Solicitud) -> int:
    base = sol.presupuesto or simulate_price(rng, sol.categoria)
    return max(20000, int(round((base * rng.uniform(0.85, 1.15)) / 1000.0) * 1000))


def create_offers_and_contracts(
    rng: random.Random,
    users: dict[str, list[User]],
    solicitudes: list[dict[str, Any]],
    sizes: Sizes,
) -> dict[str, Any]:
    specs: list[dict[str, Any]] = []
    accepted_by_sol: dict[int, dict[str, Any]] = {}
    cancel_accepted_limit = sizes.cancelado + sizes.marcado
    assigned_accepted_limit = sizes.completado_pendiente + sizes.pendiente
    cancel_seen = 0

    for item in solicitudes:
        sol: Solicitud = item["sol"]
        state: EstadoSolicitud = item["state"]
        used: set[int] = set()
        accepted = False
        accepted_pds: User | None = None
        accepted_spec: dict[str, Any] | None = None
        if state in (EstadoSolicitud.COMPLETADO, EstadoSolicitud.EN_PROGRESO, EstadoSolicitud.ASIGNADA):
            accepted = True
        elif state == EstadoSolicitud.CANCELADO:
            cancel_seen += 1
            accepted = cancel_seen <= cancel_accepted_limit

        if state == EstadoSolicitud.COMPLETADO:
            total = rng.choice([3, 4])
        elif state in (EstadoSolicitud.EN_PROGRESO, EstadoSolicitud.ASIGNADA, EstadoSolicitud.PUBLICADO):
            total = 2
        elif state == EstadoSolicitud.CANCELADO:
            total = 2 if accepted else 1
        else:
            total = 0

        if accepted:
            pds = choose_provider(rng, users["pds"], item["category"], used)
            used.add(pds.id)
            accepted_pds = pds
            created = clamp_dt(item["created"] + timedelta(hours=rng.randint(1, 48)), NOW - timedelta(hours=1))
            amount = offer_amount(rng, sol)
            accepted_spec = {
                "sol": sol,
                "pds": pds,
                "estado": EstadoOferta.ACEPTADA.value,
                "monto": amount,
                "created": created,
                "message": rng.choice(MENSAJES_OFERTA),
            }
            specs.append(accepted_spec)

        extras = max(0, total - (1 if accepted else 0))
        for _ in range(extras):
            pds = choose_provider(rng, users["pds"], item["category"], used)
            used.add(pds.id)
            created = clamp_dt(item["created"] + timedelta(hours=rng.randint(2, 96)), NOW - timedelta(hours=1))
            if state == EstadoSolicitud.PUBLICADO:
                estado = rng.choices(
                    [EstadoOferta.PENDIENTE.value, EstadoOferta.CONTRAOFERTA.value],
                    weights=[65, 35],
                    k=1,
                )[0]
            elif state == EstadoSolicitud.CANCELADO:
                estado = rng.choice([EstadoOferta.RECHAZADA.value, EstadoOferta.CANCELADA.value])
            else:
                estado = rng.choices(
                    [EstadoOferta.RECHAZADA.value, EstadoOferta.CANCELADA.value, EstadoOferta.PENDIENTE.value],
                    weights=[70, 20, 10],
                    k=1,
                )[0]
            amount = offer_amount(rng, sol)
            spec = {
                "sol": sol,
                "pds": pds,
                "estado": estado,
                "monto": amount,
                "created": created,
                "message": rng.choice(MENSAJES_OFERTA),
            }
            if estado == EstadoOferta.CONTRAOFERTA.value:
                spec["contra_monto"] = max(20000, int(amount * rng.uniform(0.9, 1.12)))
                spec["contra_mensaje"] = "Puedo ajustar el valor si coordinamos esta semana."
                spec["contra_fecha_deseada"] = sol.fecha_deseada
                spec["contra_horario"] = sol.horario
            specs.append(spec)

        if accepted_spec is not None:
            accepted_by_sol[sol.id] = accepted_spec

    if len(specs) > sizes.ofertas:
        removable = [s for s in reversed(specs) if s["estado"] != EstadoOferta.ACEPTADA.value]
        while len(specs) > sizes.ofertas and removable:
            target = removable.pop()
            specs.remove(target)
    elif len(specs) < sizes.ofertas:
        eligible = [
            item
            for item in solicitudes
            if item["state"] in (EstadoSolicitud.PUBLICADO, EstadoSolicitud.ASIGNADA)
        ]
        while len(specs) < sizes.ofertas and eligible:
            item = rng.choice(eligible)
            sol = item["sol"]
            used = {s["pds"].id for s in specs if s["sol"].id == sol.id}
            if len(used) >= len(users["pds"]):
                continue
            pds = choose_provider(rng, users["pds"], item["category"], used)
            created = clamp_dt(item["created"] + timedelta(hours=rng.randint(1, 72)), NOW - timedelta(hours=1))
            specs.append(
                {
                    "sol": sol,
                    "pds": pds,
                    "estado": EstadoOferta.PENDIENTE.value,
                    "monto": offer_amount(rng, sol),
                    "created": created,
                    "message": rng.choice(MENSAJES_OFERTA),
                }
            )

    offers: list[Oferta] = []
    for spec in specs:
        row = Oferta(
            solicitud_id=spec["sol"].id,
            pds_id=spec["pds"].id,
            monto=spec["monto"],
            mensaje=spec["message"],
            fecha_deseada=spec["sol"].fecha_deseada,
            horario=spec["sol"].horario,
            estado=spec["estado"],
            contra_monto=spec.get("contra_monto"),
            contra_mensaje=spec.get("contra_mensaje"),
            contra_fecha_deseada=spec.get("contra_fecha_deseada"),
            contra_horario=spec.get("contra_horario"),
            created_at=spec["created"],
            updated_at=clamp_dt(spec["created"] + timedelta(hours=rng.randint(1, 24)), NOW),
        )
        db.session.add(row)
        offers.append(row)
        spec["row"] = row
    db.session.flush()

    accepted_rows = {
        spec["sol"].id: spec
        for spec in specs
        if spec["estado"] == EstadoOferta.ACEPTADA.value
    }

    contracts: list[Contract] = []
    contract_meta_rows: list[dict[str, Any]] = []
    assigned_seen = 0
    cancelled_seen = 0
    for item in solicitudes:
        sol: Solicitud = item["sol"]
        state: EstadoSolicitud = item["state"]
        accepted_spec = accepted_rows.get(sol.id)
        if accepted_spec is None:
            continue
        offer: Oferta = accepted_spec["row"]
        contract_state: EstadoContrato | None = None
        if state == EstadoSolicitud.COMPLETADO:
            contract_state = EstadoContrato.COMPLETADO
        elif state == EstadoSolicitud.EN_PROGRESO:
            contract_state = EstadoContrato.EN_PROGRESO
        elif state == EstadoSolicitud.ASIGNADA:
            assigned_seen += 1
            if assigned_seen <= sizes.completado_pendiente:
                contract_state = EstadoContrato.COMPLETADO_PENDIENTE
            elif assigned_seen <= assigned_accepted_limit:
                contract_state = EstadoContrato.PENDIENTE
        elif state == EstadoSolicitud.CANCELADO:
            cancelled_seen += 1
            if cancelled_seen <= sizes.cancelado:
                contract_state = EstadoContrato.CANCELADO
            elif cancelled_seen <= cancel_accepted_limit:
                contract_state = EstadoContrato.MARCADO

        if contract_state is None:
            continue

        created = clamp_dt(offer.created_at + timedelta(days=1), NOW - timedelta(days=1))
        inicio = None
        fin = None
        confirmado = None
        motivo = None
        if contract_state == EstadoContrato.COMPLETADO:
            inicio = clamp_dt(created + timedelta(hours=rng.randint(2, 30)), NOW - timedelta(days=2))
            fin = clamp_dt(inicio + timedelta(days=rng.randint(1, 12)), NOW - timedelta(days=1))
            confirmado = clamp_dt(fin + timedelta(hours=rng.randint(1, 48)), NOW)
        elif contract_state == EstadoContrato.COMPLETADO_PENDIENTE:
            inicio = clamp_dt(created + timedelta(hours=rng.randint(2, 30)), NOW - timedelta(days=1))
            fin = clamp_dt(inicio + timedelta(days=rng.randint(1, 5)), NOW - timedelta(hours=6))
        elif contract_state == EstadoContrato.EN_PROGRESO:
            inicio = clamp_dt(created + timedelta(hours=rng.randint(2, 30)), NOW - timedelta(hours=6))
        elif contract_state in (EstadoContrato.CANCELADO, EstadoContrato.MARCADO):
            motivo = rng.choice(
                [
                    "El solicitante cancelo por cambio de planes.",
                    "No fue posible acordar el horario de ejecucion.",
                    "El PDS no pudo desplazarse a la zona.",
                ]
            )

        contract = Contract(
            service_id=sol.id,
            proveedor_id=offer.pds_id,
            solicitante_id=sol.solicitante_id,
            estado=contract_state,
            motivo_cancelacion=motivo,
            inicio_en=inicio,
            fin_en=fin,
            confirmado_en=confirmado,
            creado_en=created,
            actualizado_en=clamp_dt(
                confirmado or fin or inicio or created,
                NOW,
            ),
        )
        db.session.add(contract)
        contracts.append(contract)
        contract_meta_rows.append(
            {
                "contract": contract,
                "sol": sol,
                "offer": offer,
                "pds": accepted_spec["pds"],
                "state": contract_state,
            }
        )

    db.session.flush()
    contract_meta = {row["contract"].id: row for row in contract_meta_rows}
    db.session.commit()
    print(f"Ofertas: {len(offers)}; contratos: {len(contracts)}")
    return {
        "offers": offers,
        "contracts": contracts,
        "contract_meta": contract_meta,
        "accepted_by_sol": accepted_rows,
    }


def create_chambas(
    rng: random.Random,
    contract_meta: dict[int, dict[str, Any]],
    users: dict[str, list[User]],
) -> list[Chamba]:
    rows: list[Chamba] = []
    progress_state_cycle: list[EstadoChamba] = (
        [EstadoChamba.PROGRAMADA] * 15
        + [EstadoChamba.EN_PROCESO] * 20
        + [EstadoChamba.EN_EJECUCION] * 10
        + [EstadoChamba.PAUSADA] * 5
    )
    progress_index = 0
    adendas_added = 0

    for meta in contract_meta.values():
        contract: Contract = meta["contract"]
        state: EstadoContrato = meta["state"]
        if state == EstadoContrato.COMPLETADO:
            chamba_state = EstadoChamba.FINALIZADA
        elif state == EstadoContrato.COMPLETADO_PENDIENTE:
            chamba_state = EstadoChamba.PENDIENTE_VALIDACION
        elif state == EstadoContrato.EN_PROGRESO:
            chamba_state = progress_state_cycle[progress_index % len(progress_state_cycle)]
            progress_index += 1
        else:
            continue

        activation = clamp_dt(contract.creado_en + timedelta(hours=rng.randint(1, 24)), NOW)
        start = None
        request_close = None
        validation = None
        liquidation = None
        finalization = None
        previous = None
        if chamba_state in (
            EstadoChamba.EN_PROCESO,
            EstadoChamba.EN_EJECUCION,
            EstadoChamba.PAUSADA,
            EstadoChamba.PENDIENTE_VALIDACION,
            EstadoChamba.FINALIZADA,
        ):
            start = clamp_dt(activation + timedelta(hours=rng.randint(2, 48)), NOW - timedelta(hours=2))
        if chamba_state == EstadoChamba.PAUSADA:
            previous = EstadoChamba.EN_PROCESO
        if chamba_state in (EstadoChamba.PENDIENTE_VALIDACION, EstadoChamba.FINALIZADA):
            request_close = clamp_dt((start or activation) + timedelta(days=rng.randint(1, 6)), NOW - timedelta(hours=1))
        if chamba_state == EstadoChamba.FINALIZADA:
            validation = clamp_dt(request_close + timedelta(hours=rng.randint(2, 48)), NOW)
            liquidation = clamp_dt(validation + timedelta(hours=rng.randint(1, 24)), NOW)
            finalization = clamp_dt(liquidation + timedelta(hours=rng.randint(1, 24)), NOW)

        evidence_in = [
            f"https://{SIM_DOMAIN}/chambas/{contract.id}/entrada-{j}.jpg"
            for j in range(1, rng.randint(2, 4))
        ]
        evidence_out = (
            [f"https://{SIM_DOMAIN}/chambas/{contract.id}/salida-{j}.jpg" for j in range(1, rng.randint(2, 4))]
            if chamba_state in (EstadoChamba.PENDIENTE_VALIDACION, EstadoChamba.FINALIZADA)
            else []
        )
        novedades = []
        if chamba_state in (EstadoChamba.EN_EJECUCION, EstadoChamba.PAUSADA):
            novedades.append(
                {
                    "fecha": (start or activation).isoformat(),
                    "tipo": rng.choice(["retraso", "material", "acceso", "seguridad"]),
                    "descripcion": "Novedad reportada durante la ejecucion del trabajo.",
                }
            )
        adendas = []
        if adendas_added < 10 and chamba_state in (EstadoChamba.EN_PROCESO, EstadoChamba.FINALIZADA, EstadoChamba.PENDIENTE_VALIDACION):
            adendas_added += 1
            adendas.append(
                {
                    "fecha": (start or activation).isoformat(),
                    "descripcion": rng.choice(
                        ["Trabajo adicional de pintura", "Instalacion de punto electrico", "Reparacion de humedad", "Cambio de cerradura"]
                    ),
                    "monto_extra": rng.randrange(30000, 120000, 5000),
                    "tiempo_extra": rng.choice(["1 dia", "2 dias", "4 horas", "medio dia"]),
                }
            )

        row = Chamba(
            contract_id=contract.id,
            estado=chamba_state,
            estado_previo=previous,
            fecha_activacion=activation,
            fecha_inicio_obra=start,
            fecha_solicitud_cierre=request_close,
            fecha_validacion=validation,
            fecha_liquidacion=liquidation,
            fecha_finalizacion=finalization,
            evidencia_entrada=evidence_in,
            evidencia_salida=evidence_out,
            adendas=adendas,
            novedades=novedades,
            pago_confirmado_solicitante=chamba_state == EstadoChamba.FINALIZADA,
            pago_confirmado_prestador=chamba_state == EstadoChamba.FINALIZADA,
            pago_directo_confirmado=chamba_state == EstadoChamba.FINALIZADA,
            pago_monto_final=int(meta["offer"].monto or 0) if chamba_state == EstadoChamba.FINALIZADA else None,
            rating_estrellas=None,
            rating_comentario=None,
            habilidades_validadas=[],
            creado_en=activation,
            actualizado_en=finalization or validation or request_close or start or activation,
        )
        db.session.add(row)
        rows.append(row)
    db.session.flush()
    db.session.commit()
    print(f"Chambas: {len(rows)}")
    return rows


def create_maranas(
    rng: random.Random,
    chambas: list[Chamba],
    contract_meta: dict[int, dict[str, Any]],
    users: dict[str, list[User]],
) -> list[Marana]:
    eligible = [c for c in chambas if c.adendas]
    if not eligible:
        eligible = chambas[: min(10, len(chambas))]
        for chamba in eligible:
            if not chamba.adendas:
                chamba.adendas = [
                    {
                        "fecha": (chamba.fecha_activacion or NOW).isoformat(),
                        "descripcion": "Trabajo adicional solicitado por el cliente.",
                        "monto_extra": rng.randrange(30000, 100000, 5000),
                        "tiempo_extra": "1 dia",
                    }
                ]
    rows: list[Marana] = []
    statuses = (
        [EstadoMarana.PUBLICADO] * 4
        + [EstadoMarana.ASIGNADO] * 3
        + [EstadoMarana.PAGADO] * 2
        + [EstadoMarana.CANCELADO] * 1
    )
    rng.shuffle(statuses)

    contract_by_id = {meta["contract"].id: meta for meta in contract_meta.values()}
    for i, chamba in enumerate(eligible[: len(statuses)]):
        meta = contract_by_id[chamba.contract_id]
        sol: Solicitud = meta["sol"]
        state = statuses[i]
        adenda = chamba.adendas[0]
        categoria = rng.choice([c for c in CATEGORIAS if c != sol.categoria])
        pds = choose_provider(rng, users["pds"], categoria, {meta["pds"].id}) if state in (
            EstadoMarana.ASIGNADO,
            EstadoMarana.PAGADO,
        ) else None
        created = clamp_dt((chamba.fecha_inicio_obra or chamba.fecha_activacion or NOW) + timedelta(hours=rng.randint(1, 24)), NOW - timedelta(hours=1))
        row = Marana(
            chamba_id=chamba.id,
            adenda_idx=0,
            solicitante_id=sol.solicitante_id,
            titulo=f"Marana de {categoria} en {sol.ubicacion}",
            categoria=categoria,
            descripcion=f"Trabajo adicional derivado de la chamba #{chamba.id}: {adenda['descripcion']}.",
            presupuesto=int(adenda.get("monto_extra") or 50000),
            ubicacion=sol.ubicacion,
            fecha_deseada=created.date() + timedelta(days=rng.randint(1, 8)),
            horario=sol.horario,
            estado=state,
            pago_confirmado_solicitante=state == EstadoMarana.PAGADO,
            pago_confirmado_prestador=state == EstadoMarana.PAGADO,
            pago_monto_final=int(adenda.get("monto_extra") or 50000) if state == EstadoMarana.PAGADO else None,
            pds_asignado_id=pds.id if pds else None,
            fecha_asignacion=clamp_dt(created + timedelta(hours=rng.randint(2, 48)), NOW) if pds else None,
            fecha_entrega=clamp_dt(created + timedelta(days=rng.randint(2, 6)), NOW) if state in (EstadoMarana.COMPLETADO, EstadoMarana.PAGADO) else None,
            fecha_pago=clamp_dt(created + timedelta(days=rng.randint(3, 8)), NOW) if state == EstadoMarana.PAGADO else None,
            creado_en=created,
            actualizado_en=clamp_dt(created + timedelta(days=rng.randint(1, 8)), NOW),
        )
        db.session.add(row)
        rows.append(row)
    db.session.flush()

    offers: list[MaranaOferta] = []
    for row in rows:
        used: set[int] = set()
        if row.pds_asignado_id:
            used.add(row.pds_asignado_id)
        for j in range(2):
            pds = choose_provider(rng, users["pds"], row.categoria, used)
            used.add(pds.id)
            if row.estado in (EstadoMarana.ASIGNADO, EstadoMarana.COMPLETADO, EstadoMarana.PAGADO):
                estado = EstadoMaranaOferta.ACEPTADA.value if pds.id == row.pds_asignado_id else EstadoMaranaOferta.RECHAZADA.value
            elif row.estado == EstadoMarana.PUBLICADO:
                estado = EstadoMaranaOferta.PENDIENTE.value
            else:
                estado = EstadoMaranaOferta.RECHAZADA.value
            offers.append(
                MaranaOferta(
                    marana_id=row.id,
                    pds_id=pds.id,
                    monto=max(20000, int((row.presupuesto or 50000) * rng.uniform(0.85, 1.15))),
                    mensaje=rng.choice(MENSAJES_OFERTA),
                    estado=estado,
                    created_at=clamp_dt(row.creado_en + timedelta(hours=rng.randint(1, 24)), NOW),
                    updated_at=clamp_dt(row.creado_en + timedelta(hours=rng.randint(2, 48)), NOW),
                )
            )
    add_all_batched(offers, 100)
    db.session.commit()
    print(f"Maranas: {len(rows)}; ofertas de marana: {len(offers)}")
    return rows


def create_payments_and_milestones(
    rng: random.Random,
    contracts: list[Contract],
    contract_meta: dict[int, dict[str, Any]],
) -> tuple[list[Payment], list[Milestone], list[Modalidad]]:
    payments: list[Payment] = []
    completed = [c for c in contracts if c.estado == EstadoContrato.COMPLETADO]
    pending_validation = [c for c in contracts if c.estado == EstadoContrato.COMPLETADO_PENDIENTE]
    cancelled = [c for c in contracts if c.estado == EstadoContrato.CANCELADO]
    marked = [c for c in contracts if c.estado == EstadoContrato.MARCADO]
    in_progress = [c for c in contracts if c.estado == EstadoContrato.EN_PROGRESO]

    payment_plan: list[tuple[Contract, EstadoPago]] = []
    payment_plan += [(c, EstadoPago.COMPLETADO) for c in completed]
    payment_plan += [(c, EstadoPago.PENDIENTE) for c in pending_validation]
    payment_plan += [(c, EstadoPago.REEMBOLSADO) for c in cancelled]
    payment_plan += [(c, EstadoPago.REEMBOLSADO) for c in marked]
    payment_plan += [(c, EstadoPago.REEMBOLSADO) for c in in_progress[:15]]
    payment_plan += [(c, EstadoPago.FALLIDO) for c in in_progress[15:25]]

    for contract, estado in payment_plan:
        meta = contract_meta[contract.id]
        amount = int(meta["offer"].monto or contract.service.presupuesto or 150000)
        created = clamp_dt(contract.creado_en + timedelta(hours=rng.randint(1, 48)), NOW)
        payments.append(
            Payment(
                contract_id=contract.id,
                monto=amount,
                comision_pds=int(round(amount * 0.12)) if amount >= 50000 else 0,
                comision_solicitante=int(round(amount * 0.08)) if amount >= 50000 else 0,
                estado=estado,
                pasarela="mock",
                referencia_pasarela=f"SIM-PAY-{contract.id:05d}",
                motivo_reembolso="Reembolso simulado por cancelacion." if estado == EstadoPago.REEMBOLSADO else None,
                creado_en=created,
                actualizado_en=clamp_dt(created + timedelta(days=rng.randint(0, 10)), NOW),
            )
        )
    add_all_batched(payments, 200)

    milestone_contracts = (completed + in_progress)[:20]
    milestones: list[Milestone] = []
    for idx, contract in enumerate(milestone_contracts):
        meta = contract_meta[contract.id]
        total = int(meta["offer"].monto or 200000)
        first = int(total * 0.5)
        second = total - first
        for number, amount in ((1, first), (2, second)):
            state = [EstadoHito.APROBADO, EstadoHito.PENDIENTE, EstadoHito.RECHAZADO][(idx + number) % 3]
            milestones.append(
                Milestone(
                    contract_id=contract.id,
                    numero=number,
                    descripcion=f"Hito {number} del contrato #{contract.id}",
                    monto=amount,
                    estado=state,
                    aprobado_en=clamp_dt(contract.creado_en + timedelta(days=number * 2), NOW) if state == EstadoHito.APROBADO else None,
                    created_at=clamp_dt(contract.creado_en + timedelta(days=number), NOW),
                )
            )
    add_all_batched(milestones, 100)

    modalidades: list[Modalidad] = []
    existing_modalidades = {row[0] for row in db.session.query(Modalidad.service_id).all()}
    for meta in contract_meta.values():
        sol: Solicitud = meta["sol"]
        if sol.id in existing_modalidades:
            continue
        tipo = TipoModalidad.A_COMISION if rng.random() < 0.7 else TipoModalidad.B_SIN_COMISION
        modalidades.append(
            Modalidad(
                service_id=sol.id,
                tipo=tipo,
                monedas_requeridas=rng.randint(1, 5) if tipo == TipoModalidad.B_SIN_COMISION else None,
                created_at=clamp_dt(sol.creado_en + timedelta(hours=rng.randint(1, 12)), NOW),
            )
        )
    existing_modalidades.update(m.service_id for m in modalidades)
    missing = [
        s
        for s in Solicitud.query.all()
        if s.id not in existing_modalidades
    ]
    for sol in missing:
        modalidades.append(
            Modalidad(
                service_id=sol.id,
                tipo=TipoModalidad.A_COMISION,
                monedas_requeridas=None,
                created_at=clamp_dt(sol.creado_en + timedelta(hours=rng.randint(1, 12)), NOW),
            )
        )
    add_all_batched(modalidades, 400)
    db.session.commit()
    print(f"Pagos: {len(payments)}; hitos: {len(milestones)}; modalidades: {len(modalidades)}")
    return payments, milestones, modalidades


def create_ratings(
    rng: random.Random,
    contracts: list[Contract],
    contract_meta: dict[int, dict[str, Any]],
    chambas: list[Chamba],
    negocios: list[Negocio],
    users: dict[str, list[User]],
) -> tuple[list[Rating], list[NegocioRating]]:
    ratings: list[Rating] = []
    completed = [c for c in contracts if c.estado == EstadoContrato.COMPLETADO]
    in_progress = [c for c in contracts if c.estado == EstadoContrato.EN_PROGRESO][:20]

    for contract in completed:
        meta = contract_meta[contract.id]
        sol: Solicitud = meta["sol"]
        pds: User = meta["pds"]
        base = contract.fin_en or contract.creado_en + timedelta(days=2)
        for autor, calificado in ((sol.solicitante_id, pds.id), (pds.id, sol.solicitante_id)):
            puntaje = rng.choices([5, 4, 3, 2, 1], weights=[55, 30, 10, 4, 1], k=1)[0]
            ratings.append(
                Rating(
                    service_id=sol.id,
                    autor_id=autor,
                    calificado_id=calificado,
                    puntaje=puntaje,
                    comentario=rng.choice(COMENTARIOS_RATING),
                    reportado=rng.random() < 0.02,
                    creado_en=clamp_dt(base + timedelta(hours=rng.randint(1, 72)), NOW),
                )
            )
    for contract in in_progress:
        meta = contract_meta[contract.id]
        sol: Solicitud = meta["sol"]
        pds: User = meta["pds"]
        ratings.append(
            Rating(
                service_id=sol.id,
                autor_id=sol.solicitante_id,
                calificado_id=pds.id,
                puntaje=rng.choices([5, 4, 3], weights=[50, 40, 10], k=1)[0],
                comentario=rng.choice(COMENTARIOS_RATING),
                reportado=False,
                creado_en=clamp_dt((contract.inicio_en or contract.creado_en) + timedelta(days=1), NOW),
            )
        )
    add_all_batched(ratings, 300)

    rows = db.session.query(
        Rating.calificado_id, func.avg(Rating.puntaje)
    ).group_by(Rating.calificado_id).all()
    averages = {user_id: round(float(avg), 2) for user_id, avg in rows}
    for user in users["pds"] + users["solicitantes"] + users["merchants"]:
        user.profile.calificacion_promedio = averages.get(user.id, 0.0)

    chamba_by_contract = {c.contract_id: c for c in chambas}
    for contract in completed:
        chamba = chamba_by_contract.get(contract.id)
        if chamba is None:
            continue
        owner_rating = next(
            (r for r in ratings if r.service_id == contract.service_id and r.autor_id == contract.solicitante_id),
            None,
        )
        if owner_rating:
            chamba.rating_estrellas = owner_rating.puntaje
            chamba.rating_comentario = owner_rating.comentario
            chamba.habilidades_validadas = list(contract_meta[contract.id]["pds"].profile.categorias or [])

    business_ratings: list[NegocioRating] = []
    for idx, negocio in enumerate(negocios):
        count = 3 + (idx % 2)
        authors = rng.sample(users["solicitantes"], k=min(len(users["solicitantes"]), count))
        for autor in authors:
            business_ratings.append(
                NegocioRating(
                    negocio_id=negocio.id,
                    autor_id=autor.id,
                    puntaje=rng.choices([5, 4, 3, 2], weights=[50, 35, 12, 3], k=1)[0],
                    comentario=rng.choice(COMENTARIOS_NEGOCIO),
                    reportado=rng.random() < 0.05,
                    creado_en=clamp_dt(negocio.creado_en + timedelta(days=rng.randint(10, 120)), NOW),
                )
            )
            if len(business_ratings) >= 40:
                break
        if len(business_ratings) >= 40:
            break
    add_all_batched(business_ratings, 100)

    business_rows = db.session.query(
        NegocioRating.negocio_id, func.avg(NegocioRating.puntaje), func.count(NegocioRating.id)
    ).group_by(NegocioRating.negocio_id).all()
    business_stats = {
        negocio_id: (round(float(avg), 2), int(total))
        for negocio_id, avg, total in business_rows
    }
    for negocio in negocios:
        avg, total = business_stats.get(negocio.id, (0.0, 0))
        negocio.calificacion_promedio = avg
        negocio.total_calificaciones = total
    db.session.commit()
    print(f"Ratings: {len(ratings)} solicitud; {len(business_ratings)} negocio")
    return ratings, business_ratings


def create_kyc_portfolio_badges_trust(
    rng: random.Random,
    users: dict[str, list[User]],
    sizes: Sizes,
) -> None:
    docs: list[DocumentoUsuario] = []
    pds_docs = DocumentoRequerido.query.filter_by(rol="pds").order_by(DocumentoRequerido.orden).all()
    sol_docs = DocumentoRequerido.query.filter_by(rol="solicitante").order_by(DocumentoRequerido.orden).all()
    required_pds = [d for d in pds_docs if d.obligatorio]
    required_sol = [d for d in sol_docs if d.obligatorio]
    reviewer = next((u for u in users["staff"] if u.rol == RolUsuario.VERIFICADOR), users["staff"][0])

    for idx, user in enumerate(users["pds"][: sizes.kyc_pds]):
        for j, required in enumerate(required_pds):
            state = "aprobado" if idx < 68 else rng.choices(["aprobado", "enviado", "rechazado"], weights=[75, 18, 7], k=1)[0]
            sent = clamp_dt(NOW - timedelta(days=rng.randint(1, 180)), NOW)
            docs.append(
                DocumentoUsuario(
                    user_id=user.id,
                    documento_requerido_id=required.id,
                    documento_clave=required.clave,
                    instancia=None,
                    rol="pds",
                    estado=state,
                    url=f"https://{SIM_DOMAIN}/kyc/pds{idx + 1:03d}/{required.clave}.pdf",
                    archivo_base64=None,
                    nombre_archivo=f"{required.clave}.pdf",
                    tipo_mime="application/pdf",
                    fecha_envio=sent,
                    revisado_en=clamp_dt(sent + timedelta(days=rng.randint(0, 8)), NOW) if state in ("aprobado", "rechazado") else None,
                    revisor_id=reviewer.id if state in ("aprobado", "rechazado") else None,
                    nota="Documento verificado en simulacion." if state == "aprobado" else ("Requiere correccion." if state == "rechazado" else None),
                )
            )

    for idx, user in enumerate(users["solicitantes"][: sizes.kyc_solicitantes]):
        for required in required_sol:
            state = rng.choices(["aprobado", "enviado", "rechazado"], weights=[70, 25, 5], k=1)[0]
            sent = clamp_dt(NOW - timedelta(days=rng.randint(1, 120)), NOW)
            docs.append(
                DocumentoUsuario(
                    user_id=user.id,
                    documento_requerido_id=required.id,
                    documento_clave=required.clave,
                    instancia=None,
                    rol="solicitante",
                    estado=state,
                    url=f"https://{SIM_DOMAIN}/kyc/sol{idx + 1:03d}/{required.clave}.pdf",
                    archivo_base64=None,
                    nombre_archivo=f"{required.clave}.pdf",
                    tipo_mime="application/pdf",
                    fecha_envio=sent,
                    revisado_en=clamp_dt(sent + timedelta(days=rng.randint(0, 5)), NOW) if state in ("aprobado", "rechazado") else None,
                    revisor_id=reviewer.id if state in ("aprobado", "rechazado") else None,
                    nota="Documento verificado en simulacion." if state == "aprobado" else None,
                )
            )
    add_all_batched(docs, 400)

    portfolio: list[PortfolioItem] = []
    for idx, user in enumerate(users["pds"]):
        cats = user.profile.categorias or ["otros"]
        for j in range(2):
            state = rng.choices(["aprobado", "pendiente_revision", "rechazado"], weights=[85, 10, 5], k=1)[0]
            portfolio.append(
                PortfolioItem(
                    pds_id=user.id,
                    titulo=f"Trabajo de {cats[j % len(cats)]} #{j + 1}",
                    descripcion="Registro fotografico de un trabajo realizado en Valledupar.",
                    tipo=["foto", "video", "documento"][j % 3],
                    categoria=cats[j % len(cats)],
                    s3_key=f"portfolio/{user.id}/trabajo-{j + 1}.jpg",
                    url=f"https://{SIM_DOMAIN}/portfolio/{user.id}/trabajo-{j + 1}.jpg",
                    file_size_bytes=rng.randint(250000, 2500000),
                    mime_type="image/jpeg",
                    estado=state,
                    verificado_por=reviewer.id if state == "aprobado" else None,
                    verificado_en=clamp_dt(NOW - timedelta(days=rng.randint(1, 60)), NOW) if state == "aprobado" else None,
                    vistas=rng.randint(0, 400),
                    created_at=clamp_dt(NOW - timedelta(days=rng.randint(1, 200)), NOW),
                )
            )
    add_all_batched(portfolio, 400)

    badges: list[Badge] = []
    for user in users["pds"]:
        for badge_type in rng.sample(BADGE_CYCLE, k=2):
            badges.append(
                Badge(
                    usuario_id=user.id,
                    tipo=badge_type.value,
                    activo=True,
                    otorgado_en=clamp_dt(NOW - timedelta(days=rng.randint(1, 200)), NOW),
                )
            )
    add_all_batched(badges, 400)

    contract_counts = dict(
        db.session.query(Contract.proveedor_id, func.count(Contract.id))
        .filter(Contract.estado == EstadoContrato.COMPLETADO)
        .group_by(Contract.proveedor_id)
        .all()
    )
    portfolio_counts = dict(
        db.session.query(PortfolioItem.pds_id, func.count(PortfolioItem.id))
        .filter(PortfolioItem.estado == "aprobado")
        .group_by(PortfolioItem.pds_id)
        .all()
    )
    trust_rows: list[TrustScore] = []
    for user in users["pds"]:
        rating_score = (user.profile.calificacion_promedio or 0.0) / 5.0
        completed_count = int(contract_counts.get(user.id, 0))
        portfolio_quality = min(int(portfolio_counts.get(user.id, 0)) / 10.0, 1.0)
        referidos = rng.randint(0, 5)
        score = round(
            0.25 * (1 if user.profile.verificado else 0)
            + 0.25 * min(rating_score, 1.0)
            + 0.20 * min(completed_count / 50.0, 1.0)
            + 0.15 * portfolio_quality
            + 0.15 * min(referidos / 10.0, 1.0),
            4,
        )
        if score >= 0.8:
            nivel = "experto"
        elif score >= 0.6:
            nivel = "verificado"
        elif score >= 0.4:
            nivel = "confiable"
        else:
            nivel = "nuevo"
        trust_rows.append(
            TrustScore(
                pds_id=user.id,
                kyc_verificado=bool(user.profile.verificado),
                portfolio_calidad=portfolio_quality,
                rating_score=rating_score,
                contratos_completados=completed_count,
                referidos_count=referidos,
                puntuacion=score,
                nivel=nivel,
                componentes_json={
                    "kyc_verificado": bool(user.profile.verificado),
                    "rating_score": round(rating_score, 4),
                    "contratos_completados": completed_count,
                    "portfolio_calidad": round(portfolio_quality, 4),
                    "referidos_count": referidos,
                },
                calculado_en=NOW,
                version=1,
            )
        )
    add_all_batched(trust_rows, 300)

    verifications: list[Verification] = []
    verifier = reviewer
    for idx, user in enumerate(users["pds"][:100]):
        status = "approved" if idx < 60 else ("pending" if idx < 85 else "rejected")
        verifications.append(
            Verification(
                user_id=user.id,
                document_type="cedula",
                document_number=f"{rng.randint(10000000, 99999999)}",
                status=status,
                reviewed_by=verifier.id if status != "pending" else None,
                reviewed_at=clamp_dt(NOW - timedelta(days=rng.randint(1, 60)), NOW) if status != "pending" else None,
                reason="Documento validado en simulacion." if status == "approved" else ("Documento ilegible." if status == "rejected" else None),
                created_at=clamp_dt(NOW - timedelta(days=rng.randint(5, 150)), NOW),
            )
        )
    add_all_batched(verifications, 200)
    db.session.commit()
    print(
        f"KYC: {len(docs)} documentos; portafolio: {len(portfolio)}; "
        f"badges: {len(badges)}; trust: {len(trust_rows)}; verificaciones: {len(verifications)}"
    )


def create_communications(
    rng: random.Random,
    users: dict[str, list[User]],
    negocios: list[Negocio],
    solicitudes: list[dict[str, Any]],
    contracts: list[Contract],
    contract_meta: dict[int, dict[str, Any]],
    sizes: Sizes,
) -> None:
    logs: list[RecommendationLog] = []
    eligible_sols = [
        item["sol"]
        for item in solicitudes
        if item["state"] in (
            EstadoSolicitud.PUBLICADO,
            EstadoSolicitud.ASIGNADA,
            EstadoSolicitud.COMPLETADO,
            EstadoSolicitud.EN_PROGRESO,
        )
    ]
    if not eligible_sols:
        eligible_sols = [item["sol"] for item in solicitudes]
    for i in range(sizes.reco_logs):
        sol = rng.choice(eligible_sols)
        pds = rng.choice(users["pds"])
        logs.append(
            RecommendationLog(
                solicitud_id=sol.id,
                pds_id=pds.id,
                puntuacion=round(rng.uniform(0.25, 0.99), 4),
                ranking_pos=rng.randint(1, 10),
                features_snapshot={"distance_km": round(rng.uniform(0.3, 12), 3), "trust_score": round(rng.random(), 3)},
                modelo_nombre=rng.choice(["lightgbm_v1", "heuristic"]),
                modelo_version="sim-1",
                notificado=rng.random() < 0.9,
                respondio=rng.random() < 0.5,
                aceptado=rng.random() < 0.18,
                experiment_group=rng.choice(["A", "B"]),
                created_at=clamp_dt(sol.creado_en + timedelta(hours=rng.randint(1, 72)), NOW),
            )
        )
    add_all_batched(logs, 600)

    notification_types = [
        ("solicitud", "Nueva solicitud cerca de ti", "Hay una solicitud de {categoria} en {zona}."),
        ("oferta", "Nueva oferta recibida", "Un PDS envio una oferta para tu solicitud."),
        ("contrato", "Contrato actualizado", "El contrato cambio de estado."),
        ("pago", "Pago registrado", "Se registro un movimiento en tu billetera."),
        ("kyc", "Documento revisado", "Tu documento KYC fue revisado."),
        ("ticket", "Respuesta de soporte", "Tu ticket tiene una actualizacion."),
    ]
    notifications: list[Notification] = []
    all_users = users["pds"] + users["solicitantes"] + users["merchants"] + users["staff"]
    for _ in range(sizes.notifications):
        user = rng.choice(all_users)
        tipo, titulo, body = rng.choice(notification_types)
        sol = rng.choice(eligible_sols)
        notifications.append(
            Notification(
                user_id=user.id,
                tipo=tipo,
                titulo=titulo,
                mensaje=body.format(categoria=sol.categoria, zona=sol.ubicacion),
                datos={"solicitud_id": sol.id, "sim": True},
                leida=rng.random() < 0.55,
                creado_en=clamp_dt(NOW - timedelta(days=rng.randint(0, 90), hours=rng.randint(0, 23)), NOW),
            )
        )
    add_all_batched(notifications, 600)

    pairs: set[tuple[int, int]] = set()
    conversations: list[Conversation] = []
    pool_a = users["pds"]
    pool_b = users["solicitantes"] + users["merchants"]
    attempts = 0
    while len(conversations) < sizes.conversations and attempts < sizes.conversations * 30:
        attempts += 1
        a = rng.choice(pool_a)
        b = rng.choice(pool_b)
        if a.id == b.id:
            continue
        pair = Conversation.normalize(a.id, b.id)
        if pair in pairs:
            continue
        pairs.add(pair)
        conversations.append(
            Conversation(
                user_a_id=pair[0],
                user_b_id=pair[1],
                creado_en=clamp_dt(NOW - timedelta(days=rng.randint(0, 90)), NOW),
            )
        )
    add_all_batched(conversations, 200)
    db.session.flush()

    message_texts = [
        "Hola, vi tu solicitud y puedo ayudarte.",
        "Buenos dias, tengo disponibilidad esta semana.",
        "Podemos coordinar una visita para revisar el trabajo.",
        "El valor incluye mano de obra y materiales basicos.",
        "De acuerdo, te confirmo el horario por aqui.",
        "Gracias, quedo atento a cualquier cambio.",
        "Ya termine la actividad, adjunto evidencia.",
        "Perfecto, muchas gracias por la oportunidad.",
    ]
    messages: list[Message] = []
    for conv in conversations:
        start = conv.creado_en
        for j in range(8):
            sender = conv.user_a_id if j % 2 == 0 else conv.user_b_id
            messages.append(
                Message(
                    conversation_id=conv.id,
                    sender_id=sender,
                    contenido=message_texts[j % len(message_texts)],
                    leido=j < 6 or rng.random() < 0.5,
                    creado_en=clamp_dt(start + timedelta(hours=j * 2 + rng.randint(0, 1)), NOW),
                )
            )
    add_all_batched(messages, 800)

    tickets: list[Ticket] = []
    support_staff = [u for u in users["staff"] if u.rol in (RolUsuario.SOPORTE, RolUsuario.ADMIN)]
    for i in range(sizes.tickets):
        user = rng.choice(all_users)
        status = ["open", "pending", "closed"][i % 3]
        created = clamp_dt(NOW - timedelta(days=rng.randint(0, 120), hours=rng.randint(0, 23)), NOW)
        tickets.append(
            Ticket(
                user_id=user.id,
                subject=rng.choice(
                    ["Problema con pago", "No puedo completar mi perfil", "Solicitud de soporte", "Inconveniente con un servicio"]
                ),
                body="Ticket generado por la simulacion para probar el flujo de soporte.",
                status=status,
                priority=rng.choice(["low", "normal", "high"]),
                assigned_to=rng.choice(support_staff).id if support_staff else None,
                created_at=created,
                resolved_at=clamp_dt(created + timedelta(days=rng.randint(1, 5)), NOW) if status == "closed" else None,
            )
        )
    add_all_batched(tickets, 100)
    db.session.flush()

    disputes: list[Dispute] = []
    dispute_contracts = [c for c in contracts if c.estado in (EstadoContrato.COMPLETADO, EstadoContrato.EN_PROGRESO, EstadoContrato.CANCELADO)]
    admin = next((u for u in users["staff"] if u.rol in (RolUsuario.ADMIN, RolUsuario.SUPERADMIN)), users["staff"][0])
    for i, contract in enumerate(dispute_contracts[: sizes.disputes]):
        status = "resuelta" if i % 2 == 0 else "abierta"
        created = clamp_dt(contract.creado_en + timedelta(days=rng.randint(1, 10)), NOW)
        disputes.append(
            Dispute(
                contract_id=contract.id,
                reason=rng.choice(["El trabajo no corresponde a lo acordado.", "Cobro adicional no justificado.", "Incumplimiento de horario."]),
                status=status,
                resolved_by=admin.id if status == "resuelta" else None,
                resolved_at=clamp_dt(created + timedelta(days=rng.randint(1, 6)), NOW) if status == "resuelta" else None,
                resolution="Se acordo una solucion entre las partes." if status == "resuelta" else None,
                created_at=created,
            )
        )
    add_all_batched(disputes, 50)

    cascades: list[NotificationCascade] = []
    cascade_sols = eligible_sols[: sizes.cascades]
    for sol in cascade_sols:
        created = sol.creado_en
        state = rng.choices(["activa", "completada", "expirada", "cancelada"], weights=[35, 35, 20, 10], k=1)[0]
        cascades.append(
            NotificationCascade(
                solicitud_id=sol.id,
                fase_actual=rng.choice([1, 2, 3]),
                config_json=[
                    {"radius_km": 2.0, "delay_seconds": 300, "max_candidates": 5},
                    {"radius_km": 5.0, "delay_seconds": 600, "max_candidates": 10},
                    {"radius_km": 15.0, "delay_seconds": 900, "max_candidates": 15},
                ],
                estado=state,
                enviados_total=rng.randint(3, 30),
                respondidos_total=rng.randint(0, 12),
                timer_expira=clamp_dt(created + timedelta(minutes=30), NOW),
                started_at=created,
                completed_at=clamp_dt(created + timedelta(minutes=rng.randint(30, 180)), NOW) if state != "activa" else None,
                log_json=[
                    {"fase": 1, "enviados": rng.randint(2, 6), "radio": 2.0, "timestamp": created.isoformat()},
                ],
            )
        )
    add_all_batched(cascades, 100)

    anuncios: list[AnuncioLaboral] = []
    tipos_anuncio = ("empleo", "servicio", "producto", "oferta")
    for i in range(sizes.anuncios):
        negocio = negocios[i % len(negocios)]
        merchant = next(u for u in users["merchants"] if u.id == negocio.owner_id)
        categoria = negocio.categoria_principal
        tipo = tipos_anuncio[i % len(tipos_anuncio)]
        titulos = {
            "empleo": f"Buscamos auxiliar de {categoria}",
            "servicio": f"Servicio de {categoria} para tu negocio",
            "producto": f"Producto destacado de {categoria}",
            "oferta": f"Oferta 2x1 en {categoria}",
        }
        anuncios.append(
            AnuncioLaboral(
                negocio_id=merchant.id,
                tipo=tipo,
                titulo=titulos[tipo],
                descripcion=(
                    "Anuncio simulado para probar postulaciones y contacto."
                    if tipo == "empleo"
                    else "Anuncio simulado para probar el mapa y los banners."
                ),
                categoria=categoria,
                visible_mapa=True,
                ubicacion=negocio.direccion,
                latitud=negocio.latitud,
                longitud=negocio.longitud,
                vacantes=rng.randint(1, 3) if tipo == "empleo" else None,
                presupuesto=(
                    float(rng.randrange(20000, 120000, 5000))
                    if tipo != "empleo"
                    else None
                ),
                estado=EstadoAnuncio.PUBLICADO if i < sizes.anuncios - 2 else EstadoAnuncio.CERRADO,
                creado_en=clamp_dt(NOW - timedelta(days=rng.randint(0, 90)), NOW),
                actualizado_en=clamp_dt(NOW - timedelta(days=rng.randint(0, 20)), NOW),
            )
        )
    add_all_batched(anuncios, 100)
    db.session.flush()

    postulaciones: list[AnuncioPostulacion] = []
    anuncios_empleo = [a for a in anuncios if a.tipo == "empleo"] or anuncios
    for i in range(sizes.postulaciones):
        anuncio = rng.choice(anuncios_empleo)
        pds = rng.choice(users["pds"])
        postulaciones.append(
            AnuncioPostulacion(
                anuncio_id=anuncio.id,
                pds_id=pds.id,
                mensaje="Me interesa la vacante y tengo experiencia en el area.",
                telefono_contacto=pds.telefono,
                email_contacto=pds.email,
                estado=rng.choices(
                    [EstadoPostulacionAnuncio.PENDIENTE, EstadoPostulacionAnuncio.CONTACTADO, EstadoPostulacionAnuncio.DESCARTADO],
                    weights=[60, 25, 15],
                    k=1,
                )[0],
                created_at=clamp_dt(anuncio.creado_en + timedelta(days=rng.randint(0, 20)), NOW),
                updated_at=clamp_dt(anuncio.creado_en + timedelta(days=rng.randint(1, 30)), NOW),
            )
        )
    add_all_batched(postulaciones, 100)

    reports: list[NegocioReporte] = []
    for i in range(min(3, len(negocios := [n for n in db.session.query(Negocio).all()]))):
        negocio = negocios[i]
        reporter = rng.choice(users["solicitantes"])
        reports.append(
            NegocioReporte(
                negocio_id=negocio.id,
                reporter_id=reporter.id,
                tipo=rng.choice(["fraude", "spam", "contenido_inapropiado", "servicio_no_prestado", "otro"]),
                descripcion="Reporte simulado de negocio para pruebas de moderacion.",
                estado=rng.choice(["abierto", "investigando", "resuelto", "desestimado"]),
                ticket_id=rng.choice(tickets).id if tickets else None,
                creado_en=clamp_dt(NOW - timedelta(days=rng.randint(1, 90)), NOW),
            )
        )
    add_all_batched(reports, 20)

    audits: list[AuditLog] = []
    actions = ["aprobar_kyc", "rechazar_kyc", "suspender_usuario", "resolver_disputa", "cerrar_ticket", "editar_config"]
    for i in range(sizes.audit):
        actor = rng.choice(users["staff"])
        audits.append(
            AuditLog(
                actor_id=actor.id,
                action=rng.choice(actions),
                entity_type=rng.choice(["user", "kyc", "ticket", "dispute", "config"]),
                entity_id=rng.randint(1, 300),
                before_json=json.dumps({"sim": True, "estado": "antes"}),
                after_json=json.dumps({"sim": True, "estado": "despues"}),
                ip=f"190.0.{rng.randint(1, 250)}.{rng.randint(1, 250)}",
                created_at=clamp_dt(NOW - timedelta(days=rng.randint(0, 120)), NOW),
            )
        )
    add_all_batched(audits, 300)
    db.session.commit()
    print(
        f"Comunicaciones: {len(logs)} logs ML, {len(notifications)} notificaciones, "
        f"{len(conversations)} chats/{len(messages)} mensajes, {len(tickets)} tickets, "
        f"{len(disputes)} disputas, {len(cascades)} cascadas, {len(anuncios)} anuncios/"
        f"{len(postulaciones)} postulaciones, {len(audits)} auditorias."
    )


def update_configuration() -> None:
    upsert_config("ciudad_base", "Valledupar", "Ciudad base para la simulacion")
    upsert_config("departamento_base", "Cesar", "Departamento base")
    upsert_config("cobertura_valledupar", True, "Cobertura geografica de Valledupar")
    upsert_config("simulacion_activa", True, "Indica que la base contiene datos ficticios")
    upsert_config("comision_pds", 0.12, "Comision estandar del PDS")
    upsert_config("comision_solicitante", 0.08, "Comision estandar del solicitante")
    ensure_flags()
    db.session.commit()


def validate_and_report(
    rng: random.Random,
    sizes: Sizes,
    users: dict[str, list[User]],
    solicitudes: list[dict[str, Any]],
    contracts: list[Contract],
    run_ml_check: bool,
) -> list[str]:
    errors: list[str] = []
    sim_user_ids = [u.id for u in users["pds"] + users["solicitantes"] + users["merchants"] + users["staff"]]
    sim_sol_ids = [item["sol"].id for item in solicitudes]
    sim_contract_ids = [c.id for c in contracts]
    sim_chamba_ids = [
        row[0]
        for row in db.session.query(Chamba.id)
        .filter(Chamba.contract_id.in_(sim_contract_ids))
        .all()
    ]
    sim_conversation_ids = [
        row[0]
        for row in db.session.query(Conversation.id)
        .filter(
            (Conversation.user_a_id.in_(sim_user_ids)) | (Conversation.user_b_id.in_(sim_user_ids))
        )
        .all()
    ]
    checks = {
        "users": User.query.filter(User.email.like(f"%@{SIM_DOMAIN}")).count(),
        "profiles": Profile.query.filter(Profile.user_id.in_(sim_user_ids)).count(),
        "solicitudes": Solicitud.query.filter(Solicitud.id.in_(sim_sol_ids)).count(),
        "ofertas": Oferta.query.filter(Oferta.solicitud_id.in_(sim_sol_ids)).count(),
        "contratos": Contract.query.filter(Contract.id.in_(sim_contract_ids)).count(),
        "chambas": Chamba.query.filter(Chamba.id.in_(sim_chamba_ids)).count(),
        "pagos": Payment.query.filter(Payment.contract_id.in_(sim_contract_ids)).count(),
        "kyc": DocumentoUsuario.query.filter(DocumentoUsuario.user_id.in_(sim_user_ids)).count(),
        "notificaciones": Notification.query.filter(Notification.user_id.in_(sim_user_ids)).count(),
        "conversaciones": Conversation.query.filter(Conversation.id.in_(sim_conversation_ids)).count(),
        "mensajes": Message.query.filter(Message.conversation_id.in_(sim_conversation_ids)).count(),
    }
    if checks["users"] != sizes.pds + sizes.solicitantes + sizes.merchants + sizes.staff:
        errors.append("El numero de usuarios no coincide con el perfil.")
    if checks["profiles"] != checks["users"]:
        errors.append("Hay usuarios sin perfil.")
    if checks["solicitudes"] != sizes.solicitudes:
        errors.append("El numero de solicitudes no coincide.")
    if checks["ofertas"] != sizes.ofertas:
        errors.append(f"El numero de ofertas es {checks['ofertas']} y se esperaban {sizes.ofertas}.")
    accepted_per_sol = dict(
        db.session.query(Oferta.solicitud_id, func.count(Oferta.id))
        .filter(
            Oferta.solicitud_id.in_(sim_sol_ids),
            Oferta.estado == EstadoOferta.ACEPTADA.value,
        )
        .group_by(Oferta.solicitud_id)
        .all()
    )
    if any(count > 1 for count in accepted_per_sol.values()):
        errors.append("Hay solicitudes con mas de una oferta aceptada.")
    contracts_per_sol = dict(
        db.session.query(Contract.service_id, func.count(Contract.id))
        .filter(Contract.id.in_(sim_contract_ids))
        .group_by(Contract.service_id)
        .all()
    )
    if any(count > 1 for count in contracts_per_sol.values()):
        errors.append("Hay solicitudes con mas de un contrato.")
    expected_chambas = sizes.completadas + sizes.completado_pendiente + sizes.en_progreso
    if checks["chambas"] != expected_chambas:
        errors.append(f"El numero de chambas es {checks['chambas']} y se esperaban {expected_chambas}.")
    if Solicitud.query.filter(Solicitud.id.in_(sim_sol_ids), Solicitud.latitud.is_(None)).count():
        errors.append("Hay solicitudes sin latitud.")
    if any(c.check_password(PASSWORD) is False for c in (users["pds"][0], users["solicitantes"][0], users["merchants"][0], users["staff"][0])):
        errors.append("El login simulado no funciona para todos los roles base.")

    pds = users["pds"][0]
    print(f"Credencial PDS: {pds.email} / {PASSWORD}")
    print(f"Credencial solicitante: {users['solicitantes'][0].email} / {PASSWORD}")
    print(f"Credencial merchant: {users['merchants'][0].email} / {PASSWORD}")
    print(f"Credencial staff: {users['staff'][0].email} / {PASSWORD}")

    if run_ml_check:
        try:
            from app.ai.train import generate_training_data

            X, y, groups = generate_training_data()
            positives = int(y.sum()) if len(y) else 0
            print(f"ML: X={X.shape}, y={y.shape}, grupos={len(groups)}, positivos={positives}")
            if len(groups) < 100:
                errors.append(f"El dataset ML solo tiene {len(groups)} grupos (se esperaban >=100).")
            if positives == 0 or positives == len(y):
                errors.append("El dataset ML no tiene labels mixtos.")
        except Exception as exc:
            errors.append(f"No se pudo generar el dataset ML: {exc}")

    print("Conteos:", json.dumps(checks, ensure_ascii=False))
    return errors


def write_credentials(
    users: dict[str, list[User]],
    sizes: Sizes,
) -> None:
    docs_dir = Path(__file__).resolve().parent / "docs" / "simulacion"
    docs_dir.mkdir(parents=True, exist_ok=True)
    csv_path = docs_dir / "credenciales.csv"
    readme_path = docs_dir / "README.md"

    rows: list[dict[str, str]] = []
    for role_key, label in (
        ("pds", "pds"),
        ("solicitantes", "solicitante"),
        ("merchants", "merchant"),
        ("staff", "staff"),
    ):
        for user in users[role_key]:
            rows.append(
                {
                    "rol": user.rol.value,
                    "nombre": user.nombre or "",
                    "email": user.email,
                    "username": user.username or "",
                    "password": PASSWORD,
                    "estado": user.status,
                }
            )

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["rol", "nombre", "email", "username", "password", "estado"])
        writer.writeheader()
        writer.writerows(rows)

    readme = f"""# Simulacion Valledupar

Datos 100% ficticios generados por `seed_simulacion_valledupar.py`.

## Credenciales

- Todas las cuentas usan la contrasena: `{PASSWORD}`
- PDS: `pds001@sim.chambeapp.co` ... `pds{sizes.pds:03d}@sim.chambeapp.co`
- Solicitantes: `sol001@sim.chambeapp.co` ... `sol{sizes.solicitantes:03d}@sim.chambeapp.co`
- Merchants: `neg001@sim.chambeapp.co` ... `neg{sizes.merchants:03d}@sim.chambeapp.co`
- Staff: `staff.*@sim.chambeapp.co`
- Listado completo: `docs/simulacion/credenciales.csv`

## Volumen

- Usuarios: {len(rows)}
- Solicitudes: {sizes.solicitudes}
- Ofertas: {sizes.ofertas}
- Contratos: {sizes.completadas + sizes.en_progreso + sizes.completado_pendiente + sizes.pendiente + sizes.cancelado + sizes.marcado}
- Chambas: {sizes.completadas + sizes.completado_pendiente + sizes.en_progreso}
- Pagos: {sizes.completadas + sizes.completado_pendiente + sizes.cancelado + sizes.marcado + 25}

## Comandos

```bash
python seed_simulacion_valledupar.py --reset
python seed_simulacion_valledupar.py --reset --config app.config.TestingConfig --create-all
```

El reset elimina solo cuentas `@{SIM_DOMAIN}` y sus dependencias.

## Nota de seguridad

Estas credenciales son de simulacion. No usar en produccion.
"""
    readme_path.write_text(readme, encoding="utf-8")
    print(f"Credenciales: {csv_path}")
    print(f"README: {readme_path}")


def run(args: argparse.Namespace) -> int:
    if args.profile == "light":
        scale = 0.25
    elif args.profile == "full":
        scale = 1.0
    else:
        scale = float(args.scale)
    sizes = build_sizes(scale)

    app = create_app(args.config)
    with app.app_context():
        ensure_schema_and_catalogs(create_all=args.create_all)
        ensure_sim_isolation(reset=args.reset)
        if args.reset:
            reset_simulation()

        if db.session.query(User.id).filter(User.email.like(f"%@{SIM_DOMAIN}")).first():
            raise SystemExit("Aun existen datos de simulacion despues del reset.")

        rng = random.Random(args.seed)
        update_configuration()
        users = create_users(rng, sizes)
        create_subscriptions(rng, users)
        negocios = create_businesses(rng, users, sizes)
        create_financial_profiles(rng, users, sizes)
        solicitudes = create_solicitudes(rng, users, sizes)
        flow = create_offers_and_contracts(rng, users, solicitudes, sizes)
        chambas = create_chambas(rng, flow["contract_meta"], users)
        create_maranas(rng, chambas, flow["contract_meta"], users)
        create_payments_and_milestones(rng, flow["contracts"], flow["contract_meta"])
        create_ratings(rng, flow["contracts"], flow["contract_meta"], chambas, negocios, users)
        create_kyc_portfolio_badges_trust(rng, users, sizes)
        create_communications(
            rng,
            users,
            negocios,
            solicitudes,
            flow["contracts"],
            flow["contract_meta"],
            sizes,
        )
        db.session.commit()

        errors = validate_and_report(
            rng,
            sizes,
            users,
            solicitudes,
            flow["contracts"],
            run_ml_check=not args.skip_ml_check,
        )
        write_credentials(users, sizes)
        if errors:
            print("\nVALIDACION CON ERRORES:")
            for error in errors:
                print(f" - {error}")
            return 1
        print("\nSimulacion completada sin errores de validacion.")
        return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Siembra datos ficticios de Valledupar para ChambeApp")
    parser.add_argument("--config", default="app.config.DevelopmentConfig", help="Clase de configuracion Flask")
    parser.add_argument("--profile", choices=["normal", "light", "full"], default="normal")
    parser.add_argument("--scale", type=float, default=1.0, help="Escala personalizada (0.1 - 1.0)")
    parser.add_argument("--reset", action="store_true", help="Elimina solo datos @sim.chambeapp.co")
    parser.add_argument("--create-all", action="store_true", help="Crea el esquema si no existe")
    parser.add_argument("--seed", type=int, default=SEED, help="Semilla determinista")
    parser.add_argument("--skip-ml-check", action="store_true", help="Omite la validacion del dataset ML")
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    try:
        return run(args)
    except SystemExit:
        raise
    except Exception:
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
