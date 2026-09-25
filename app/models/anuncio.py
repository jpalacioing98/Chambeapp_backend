"""Domain models: AnuncioLaboral — oferta laboral de un negocio.

No es vinculante: solo un banner publicitario visible en el mapa de
negocios para todos los roles, que permite postulaciones de PDS y
gestión de contacto (contactar/descartar) por parte del negocio.
"""

from datetime import datetime, timezone
from enum import Enum

from app.extensions import db


class EstadoAnuncio(str, Enum):
    PUBLICADO = "publicado"
    CERRADO = "cerrado"

    @classmethod
    def values(cls):
        return [e.value for e in cls]


class EstadoPostulacionAnuncio(str, Enum):
    PENDIENTE = "pendiente"
    CONTACTADO = "contactado"
    DESCARTADO = "descartado"

    @classmethod
    def values(cls):
        return [e.value for e in cls]


class AnuncioLaboral(db.Model):
    __tablename__ = "anuncios_laborales"

    id = db.Column(db.Integer, primary_key=True)
    negocio_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    titulo = db.Column(db.String(200), nullable=False)
    descripcion = db.Column(db.Text, nullable=False)
    categoria = db.Column(db.String(120), nullable=False)
    ubicacion = db.Column(db.String(160), nullable=True)
    latitud = db.Column(db.Float, nullable=True)
    longitud = db.Column(db.Float, nullable=True)
    vacantes = db.Column(db.Integer, nullable=True)
    estado = db.Column(
        db.Enum(
            EstadoAnuncio,
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
        default=EstadoAnuncio.PUBLICADO,
    )
    creado_en = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    actualizado_en = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    negocio = db.relationship("User", foreign_keys=[negocio_id])
    postulaciones = db.relationship(
        "AnuncioPostulacion",
        back_populates="anuncio",
        cascade="all, delete-orphan",
    )


class AnuncioPostulacion(db.Model):
    """Postulación de un PDS a un anuncio (no vinculante: solo contacto)."""

    __tablename__ = "anuncios_postulaciones"

    id = db.Column(db.Integer, primary_key=True)
    anuncio_id = db.Column(
        db.Integer, db.ForeignKey("anuncios_laborales.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    pds_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    mensaje = db.Column(db.Text, nullable=True)
    # Datos de contacto del PDS (gestión de contacto del negocio).
    telefono_contacto = db.Column(db.String(40), nullable=True)
    email_contacto = db.Column(db.String(120), nullable=True)
    estado = db.Column(
        db.Enum(
            EstadoPostulacionAnuncio,
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
        default=EstadoPostulacionAnuncio.PENDIENTE,
    )
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    anuncio = db.relationship("AnuncioLaboral", back_populates="postulaciones")
    pds = db.relationship("User", foreign_keys=[pds_id])