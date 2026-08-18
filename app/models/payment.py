"""Domain model: Payment (RF-08 — Pasarela de Pagos e Ingresos)."""

from datetime import datetime, timezone
from enum import Enum

from app.extensions import db


class EstadoPago(str, Enum):
    """Estados de un pago / ciclo de escrow (RF-08)."""

    PENDIENTE = "pendiente"
    CONFIRMADO = "confirmado"
    EN_ESCROW = "en_escrow"
    LIBERADO = "liberado"
    REEMBOLSADO = "reembolsado"
    FALLIDO = "fallido"

    @classmethod
    def values(cls):
        return [e.value for e in cls]


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(
        db.Integer,
        db.ForeignKey("orders.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    monto = db.Column(db.Integer, nullable=False)  # COP
    comision = db.Column(db.Integer, nullable=False, default=0)  # COP
    estado = db.Column(
        db.Enum(EstadoPago), nullable=False, default=EstadoPago.PENDIENTE
    )
    pasarela = db.Column(db.String(50), nullable=False, default="mock")
    referencia_pasarela = db.Column(db.String(255), nullable=True)
    motivo_reembolso = db.Column(db.String(500), nullable=True)
    creado_en = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    actualizado_en = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    liberado_en = db.Column(db.DateTime, nullable=True)

    order = db.relationship("Order")

    def __repr__(self):
        return f"<Payment {self.id} order={self.order_id} estado={self.estado.value}>"
