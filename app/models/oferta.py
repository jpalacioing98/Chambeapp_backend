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
    __table_args__ = (
        db.Index("ix_ofertas_solicitud_creado", "solicitud_id", "created_at"),
        db.Index("ix_ofertas_pds_creado", "pds_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    solicitud_id = db.Column(
        db.Integer, db.ForeignKey("solicitudes.id"), nullable=False
    )
    pds_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )
    monto = db.Column(db.Float, nullable=True)
    mensaje = db.Column(db.Text, nullable=True)
    # Parámetros "a convenir" concretados por el PDS en su oferta cuando la
    # solicitud no los definió (fecha deseada / franja horaria).
    fecha_deseada = db.Column(db.Date, nullable=True)
    horario = db.Column(db.String(80), nullable=True)
    estado = db.Column(
        db.String(20), nullable=False, default=EstadoOferta.PENDIENTE.value
    )
    contra_monto = db.Column(db.Float, nullable=True)
    contra_mensaje = db.Column(db.Text, nullable=True)
    # Ajustes negociados en el chat (contraoferta) para los mismos parámetros.
    contra_fecha_deseada = db.Column(db.Date, nullable=True)
    contra_horario = db.Column(db.String(80), nullable=True)
    # Quién propuso la contraoferta vigente: "solicitante" | "pds".
    contra_autor = db.Column(db.String(20), nullable=True)
    # Aceptación bilateral: cada parte acepta el valor vigente en la
    # negociación. El acuerdo (y el contrato) se da cuando ambos aceptan.
    aceptada_por_solicitante = db.Column(
        db.Boolean, nullable=False, default=False
    )
    aceptada_por_pds = db.Column(db.Boolean, nullable=False, default=False)
    # Valor final acordado (la oferta o la contraoferta aceptada por ambas
    # partes). Sobrescribe al monto original de la solicitud.
    monto_final = db.Column(db.Float, nullable=True)
    # Condiciones acordadas durante la negociación (lista JSON) que quedan
    # incorporadas al contrato.
    condiciones = db.Column(db.JSON, nullable=True)
    fecha_aceptacion = db.Column(db.DateTime, nullable=True)
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
