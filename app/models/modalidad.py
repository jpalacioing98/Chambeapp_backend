"""Domain models: Modalidad, Milestone (RF-26, RF-29 — Modalidades de Cobro y Hitos)."""

from datetime import datetime, timezone
from enum import Enum

from app.extensions import db


class TipoModalidad(str, Enum):
    """Modalidades de cobro (RF-26)."""

    A_COMISION = "A_comision"
    B_SIN_COMISION = "B_sin_comision"

    @classmethod
    def values(cls):
        return [t.value for t in cls]


class EstadoHito(str, Enum):
    """Estados de un hito de pago (RF-29)."""

    PENDIENTE = "pendiente"
    APROBADO = "aprobado"
    RECHAZADO = "rechazado"

    @classmethod
    def values(cls):
        return [e.value for e in cls]


class Modalidad(db.Model):
    """Modalidad de cobro de una solicitud (RF-26)."""

    __tablename__ = "modalidades"

    id = db.Column(db.Integer, primary_key=True)
    service_id = db.Column(
        db.Integer, db.ForeignKey("solicitudes.id"), unique=True, nullable=False, index=True
    )
    tipo = db.Column(db.Enum(TipoModalidad), nullable=False)
    monedas_requeridas = db.Column(db.Integer, nullable=True)  # Solo para modalidad B
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    service = db.relationship("Solicitud", backref="modalidad", uselist=False)

    def __repr__(self):
        return f"<Modalidad service={self.service_id} tipo={self.tipo.value}>"


class Milestone(db.Model):
    """Hito de pago para contratos largos (RF-29)."""

    __tablename__ = "milestones"

    id = db.Column(db.Integer, primary_key=True)
    contract_id = db.Column(
        db.Integer, db.ForeignKey("contracts.id"), nullable=False, index=True
    )
    numero = db.Column(db.Integer, nullable=False)
    descripcion = db.Column(db.Text, nullable=True)
    monto = db.Column(db.Integer, nullable=False)  # COP
    estado = db.Column(
        db.Enum(EstadoHito), nullable=False, default=EstadoHito.PENDIENTE
    )
    aprobado_en = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    contract = db.relationship("Contract", backref="milestones")

    def __repr__(self):
        return f"<Milestone contract={self.contract_id} #{self.numero} estado={self.estado.value}>"
