"""Domain models: AnuncioLaboral — oferta laboral de un negocio.

Puede ser de dos modalidades:
  - "contacto": banner publicitario visible en el mapa de negocios para
    todos los roles; permite postulaciones de PDS y gestión de contacto
    (contactar/descartar) por parte del negocio. NO vinculante.
  - "contrato": oferta vinculante; el negocio elige una postulación y se
    genera un Contract (con su solicitud y chamba) que ambas partes firman.
"""

from datetime import datetime, timezone
from enum import Enum

from app.extensions import db


class ModalidadAnuncio(str, Enum):
    """Modalidad de un anuncio laboral."""

    CONTACTO = "contacto"  # solo postulación + contacto (no vinculante)
    CONTRATO = "contrato"  # postulación → contract vinculante

    @classmethod
    def values(cls):
        return [e.value for e in cls]


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
    CONTRATADO = "contratado"

    @classmethod
    def values(cls):
        return [e.value for e in cls]


class AnuncioLaboral(db.Model):
    __tablename__ = "anuncios_laborales"
    __table_args__ = (
        db.Index("ix_anuncios_estado_creado", "estado", "creado_en"),
        db.Index("ix_anuncios_negocio_creado", "negocio_id", "creado_en"),
        db.Index("ix_anuncios_modalidad_creado", "modalidad", "creado_en"),
    )

    id = db.Column(db.Integer, primary_key=True)
    negocio_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )
    titulo = db.Column(db.String(200), nullable=False)
    descripcion = db.Column(db.Text, nullable=False)
    categoria = db.Column(db.String(120), nullable=False)
    # Tipo de anuncio: empleo | servicio | producto | oferta.
    tipo = db.Column(db.String(12), nullable=False, default="empleo")
    # true → aparece en el mapa; false → solo en el perfil público.
    visible_mapa = db.Column(db.Boolean, nullable=False, default=True)
    ubicacion = db.Column(db.String(160), nullable=True)
    latitud = db.Column(db.Float, nullable=True)
    longitud = db.Column(db.Float, nullable=True)
    vacantes = db.Column(db.Integer, nullable=True)
    # Modalidad: "contacto" (actual, no vinculante) o "contrato" (vinculante).
    modalidad = db.Column(
        db.Enum(
            ModalidadAnuncio,
            values_callable=lambda enum: [e.value for e in enum],
            name="modalidadanuncio",
        ),
        nullable=False,
        default=ModalidadAnuncio.CONTACTO,
    )
    # Parámetros del contrato (requeridos cuando modalidad == "contrato").
    presupuesto = db.Column(db.Float, nullable=True)
    fecha_deseada = db.Column(db.Date, nullable=True)
    horario = db.Column(db.String(80), nullable=True)
    # Trazabilidad: ids de contratos generados desde este anuncio.
    contract_ids = db.Column(db.JSON, default=list)
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
    # Contrato generado al contratar esta postulación (modalidad "contrato").
    contract_id = db.Column(db.Integer, nullable=True, index=True)
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