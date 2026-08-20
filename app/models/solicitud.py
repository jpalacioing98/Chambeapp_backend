"""Domain models: Solicitud, Rating (RF-02, RF-03, RF-04)."""

from datetime import datetime, timezone
from enum import Enum

from app.extensions import db


class UrgenciaSolicitud(str, Enum):
    """Nivel de urgencia de una solicitud de trabajo informal ocasional."""

    BAJA = "baja"
    MEDIA = "media"
    ALTA = "alta"

    @classmethod
    def values(cls):
        return [e.value for e in cls]


class EstadoSolicitud(str, Enum):
    """Estados de una solicitud publicada en ChambeApp."""

    BORRADOR = "borrador"
    PUBLICADO = "publicado"
    EN_PROGRESO = "en_progreso"
    COMPLETADO = "completado"
    CANCELADO = "cancelado"
    # RBAC Fase 2: moderación admin.
    OCULTO = "oculto"
    RECHAZADO = "rechazado"
    # Negociación: solicitud asignada a un pds vía oferta aceptada.
    ASIGNADA = "asignada"

    @classmethod
    def values(cls):
        return [e.value for e in cls]


class Solicitud(db.Model):
    __tablename__ = "solicitudes"

    id = db.Column(db.Integer, primary_key=True)
    solicitante_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    titulo = db.Column(db.String(200), nullable=False)
    categoria = db.Column(db.String(120), nullable=False)
    descripcion = db.Column(db.Text, nullable=False)
    ubicacion = db.Column(db.String(120), nullable=False, default="Valledupar")
    # RF-04 (geo): coordenadas y dirección exacta. Solo se exponen al dueño
    # solicitante o al pds premiado (vía Contract). Nunca en listados.
    latitud = db.Column(db.Float, nullable=True)
    longitud = db.Column(db.Float, nullable=True)
    direccion = db.Column(db.String(255), nullable=True)
    presupuesto = db.Column(db.Integer, nullable=True)  # None => "a convenir"
    fecha_deseada = db.Column(db.Date, nullable=True)
    urgencia = db.Column(
        db.Enum(UrgenciaSolicitud), nullable=True, default=UrgenciaSolicitud.MEDIA
    )
    estado = db.Column(
        db.Enum(EstadoSolicitud), nullable=False, default=EstadoSolicitud.PUBLICADO
    )
    especificaciones_tecnicas = db.Column(db.JSON, nullable=True)
    imagen_360 = db.Column(db.String(500), nullable=True)
    creado_en = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    actualizado_en = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Campo transitorio (no persistido) para advertir ubicación fuera de Valledupar
    advertencia = None

    ratings = db.relationship(
        "app.models.solicitud.Rating",
        back_populates="solicitud",
        cascade="all, delete-orphan",
    )
    ofertas = db.relationship(
        "Oferta", back_populates="solicitud", cascade="all, delete-orphan"
    )


class Rating(db.Model):
    # Tabla propia de Solicitud (la del Service vive en app/models/service.py
    # con __tablename__="ratings"). Separadas para evitar colisión de metadata.
    __tablename__ = "ratings_solicitud"
    __table_args__ = (
        db.UniqueConstraint("service_id", "autor_id", name="uq_solicitud_autor"),
    )

    id = db.Column(db.Integer, primary_key=True)
    service_id = db.Column(
        db.Integer, db.ForeignKey("solicitudes.id"), nullable=False, index=True
    )
    autor_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    calificado_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    puntaje = db.Column(db.Integer, nullable=False)  # 1-5
    comentario = db.Column(db.Text, nullable=True)
    reportado = db.Column(db.Boolean, default=False, nullable=False)
    creado_en = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    solicitud = db.relationship("Solicitud", back_populates="ratings")
