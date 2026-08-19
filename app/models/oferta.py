"""Domain model: Oferta (negociación pds/solicitante).

Una Oferta es la propuesta de un pds (trabajador) para realizar la solicitud
de un solicitante (empleador). Soporta contraofertas y aceptación, lo que
desemboca en la creación de una Order (RF-07).
"""

from datetime import datetime, timezone
from enum import Enum

from app.extensions import db


class EstadoOferta(str, Enum):
    """Estados de una oferta de negociación."""

    PENDIENTE = "pendiente"
    ACEPTADA = "aceptada"
    RECHAZADA = "rechazada"
    CONTRAOFERTA = "contraoferta"
    CANCELADA = "cancelada"

    @classmethod
    def values(cls):
        return [e.value for e in cls]


class Oferta(db.Model):
    __tablename__ = "ofertas"

    id = db.Column(db.Integer, primary_key=True)
    solicitud_id = db.Column(
        db.Integer, db.ForeignKey("solicitudes.id"), nullable=False, index=True
    )
    pds_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    monto = db.Column(db.Float, nullable=True)
    mensaje = db.Column(db.Text, nullable=True)
    estado = db.Column(
        db.String(20), nullable=False, default=EstadoOferta.PENDIENTE.value
    )
    contra_monto = db.Column(db.Float, nullable=True)
    contra_mensaje = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    solicitud = db.relationship(
        "Solicitud", back_populates="ofertas"
    )
    pds = db.relationship("User", foreign_keys=[pds_id])
