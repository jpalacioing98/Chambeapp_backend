"""Modelos del módulo Negocios: Negocio, NegocioHorario, NegocioRating, NegocioReporte."""

from datetime import datetime, timezone
from enum import Enum

from app.extensions import db
from geoalchemy2 import Geometry


# ── Enums ──────────────────────────────────────────────────────────────

class TipoNegocio(str, Enum):
    COMERCIO = "comercio"           # Tienda física
    SERVICIO = "servicio"           # PDS con establecimiento
    VIRTUAL = "virtual"             # Solo online
    HIBRIDO = "hibrido"             # Físico + online


class EstadoNegocio(str, Enum):
    BORRADOR = "borrador"
    PENDIENTE_VERIFICACION = "pendiente_verificacion"
    ACTIVO = "activo"
    SUSPENDIDO = "suspendido"
    RECHAZADO = "rechazado"


class EstadoReporte(str, Enum):
    ABIERTO = "abierto"
    INVESTIGANDO = "investigando"
    RESUELTO = "resuelto"
    DESESTIMADO = "desestimado"


class TipoReporte(str, Enum):
    FRAUDE = "fraude"
    SPAM = "spam"
    CONTENIDO_INAPROPIADO = "contenido_inapropiado"
    SERVICIO_NO_PRESTADO = "servicio_no_prestado"
    OTRO = "otro"


# ── Models ─────────────────────────────────────────────────────────────

class Negocio(db.Model):
    __tablename__ = "negocios"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"),
                         nullable=False, index=True)

    # ── Identidad ──
    nombre = db.Column(db.String(150), nullable=False)
    slug = db.Column(db.String(170), unique=True, nullable=False, index=True)
    descripcion = db.Column(db.Text, nullable=True)
    tipo = db.Column(db.Enum(TipoNegocio), nullable=False,
                     default=TipoNegocio.COMERCIO)

    # ── Multimedia ──
    logo_url = db.Column(db.String(500), nullable=True)
    banner_url = db.Column(db.String(500), nullable=True)
    imagenes = db.Column(db.JSON, default=list)

    # ── Geolocalización ──
    latitud = db.Column(db.Float, nullable=False)
    longitud = db.Column(db.Float, nullable=False)
    direccion = db.Column(db.String(255), nullable=False)
    ciudad = db.Column(db.String(100), nullable=False, default="Valledupar")
    departamento = db.Column(db.String(100), nullable=True)
    radio_cobertura_km = db.Column(db.Float, default=5.0)
    geom = db.Column(Geometry("POINT", srid=4326), nullable=True)

    # ── Categoría y servicios ──
    categoria_principal = db.Column(db.String(120), nullable=False)
    categorias_secundarias = db.Column(db.JSON, default=list)
    servicios = db.Column(db.JSON, default=list)
    palabras_clave = db.Column(db.JSON, default=list)

    # ── Enlaces externos ──
    whatsapp = db.Column(db.String(30), nullable=True)
    whatsapp_mensaje_pre = db.Column(db.Text, nullable=True)
    instagram = db.Column(db.String(255), nullable=True)
    facebook = db.Column(db.String(255), nullable=True)
    tiktok = db.Column(db.String(255), nullable=True)
    sitio_web = db.Column(db.String(255), nullable=True)

    # ── Reputación ──
    calificacion_promedio = db.Column(db.Float, default=0.0)
    total_calificaciones = db.Column(db.Integer, default=0)
    verificado = db.Column(db.Boolean, default=False)

    # ── Estado ──
    estado = db.Column(db.Enum(EstadoNegocio), nullable=False,
                       default=EstadoNegocio.BORRADOR)
    motivo_rechazo = db.Column(db.Text, nullable=True)

    # ── Timestamps ──
    creado_en = db.Column(db.DateTime,
                          default=lambda: datetime.now(timezone.utc))
    actualizado_en = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ── Relaciones ──
    owner = db.relationship("User", backref="negocios")
    horarios = db.relationship(
        "NegocioHorario", back_populates="negocio",
        cascade="all, delete-orphan",
        order_by="NegocioHorario.dia_semana",
    )
    ratings = db.relationship(
        "NegocioRating", back_populates="negocio",
        cascade="all, delete-orphan",
    )
    reportes = db.relationship(
        "NegocioReporte", back_populates="negocio",
        cascade="all, delete-orphan",
    )


class NegocioHorario(db.Model):
    __tablename__ = "negocio_horarios"

    id = db.Column(db.Integer, primary_key=True)
    negocio_id = db.Column(db.Integer, db.ForeignKey("negocios.id"),
                           nullable=False, index=True)
    dia_semana = db.Column(db.Integer, nullable=False)  # 0=Lunes, 6=Domingo
    abierto = db.Column(db.Boolean, default=True)
    hora_apertura = db.Column(db.Time, nullable=True)
    hora_cierre = db.Column(db.Time, nullable=True)

    __table_args__ = (
        db.UniqueConstraint("negocio_id", "dia_semana",
                            name="uq_negocio_dia"),
    )

    negocio = db.relationship("Negocio", back_populates="horarios")


class NegocioRating(db.Model):
    __tablename__ = "negocio_ratings"

    id = db.Column(db.Integer, primary_key=True)
    negocio_id = db.Column(db.Integer, db.ForeignKey("negocios.id"),
                           nullable=False, index=True)
    autor_id = db.Column(db.Integer, db.ForeignKey("users.id"),
                         nullable=False)
    puntaje = db.Column(db.Integer, nullable=False)
    comentario = db.Column(db.Text, nullable=True)
    reportado = db.Column(db.Boolean, default=False)
    creado_en = db.Column(db.DateTime,
                          default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint("negocio_id", "autor_id",
                            name="uq_negocio_autor"),
        db.CheckConstraint("puntaje >= 1 AND puntaje <= 5",
                           name="ck_negocio_rating_puntaje"),
    )

    negocio = db.relationship("Negocio", back_populates="ratings")
    autor = db.relationship("User")


class NegocioReporte(db.Model):
    __tablename__ = "negocio_reportes"

    id = db.Column(db.Integer, primary_key=True)
    negocio_id = db.Column(db.Integer, db.ForeignKey("negocios.id"),
                           nullable=False, index=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey("users.id"),
                            nullable=False)
    tipo = db.Column(db.Enum(TipoReporte), nullable=False)
    descripcion = db.Column(db.Text, nullable=True)
    estado = db.Column(db.Enum(EstadoReporte), nullable=False,
                       default=EstadoReporte.ABIERTO)
    ticket_id = db.Column(db.Integer, db.ForeignKey("tickets.id"),
                          nullable=True)
    creado_en = db.Column(db.DateTime,
                          default=lambda: datetime.now(timezone.utc))

    negocio = db.relationship("Negocio", back_populates="reportes")
    reporter = db.relationship("User")
