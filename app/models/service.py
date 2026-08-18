"""Domain models: Service, Rating (RF-02, RF-03, RF-04)."""

from datetime import datetime, timezone
from enum import Enum

from app.extensions import db


class EstadoServicio(str, Enum):
    """Estados de un servicio publicado en ChambeApp."""

    BORRADOR = "borrador"
    PUBLICADO = "publicado"
    EN_PROGRESO = "en_progreso"
    COMPLETADO = "completado"
    CANCELADO = "cancelado"

    @classmethod
    def values(cls):
        return [e.value for e in cls]


class Service(db.Model):
    __tablename__ = "services"

    id = db.Column(db.Integer, primary_key=True)
    solicitante_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    categoria = db.Column(db.String(120), nullable=False)
    descripcion = db.Column(db.Text, nullable=False)
    ubicacion = db.Column(db.String(120), nullable=False, default="Valledupar")
    presupuesto = db.Column(db.Integer, nullable=True)  # None => "a convenir"
    estado = db.Column(
        db.Enum(EstadoServicio), nullable=False, default=EstadoServicio.PUBLICADO
    )
    especificaciones_tecnicas = db.Column(db.JSON, nullable=True)
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
        "Rating", back_populates="service", cascade="all, delete-orphan"
    )


class Rating(db.Model):
    __tablename__ = "ratings"
    __table_args__ = (
        db.UniqueConstraint("service_id", "autor_id", name="uq_service_autor"),
    )

    id = db.Column(db.Integer, primary_key=True)
    service_id = db.Column(
        db.Integer, db.ForeignKey("services.id"), nullable=False, index=True
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

    service = db.relationship("Service", back_populates="ratings")
