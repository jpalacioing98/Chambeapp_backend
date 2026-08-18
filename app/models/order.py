"""Domain models: Order (RF-07 — Gestión Contractual y Órdenes de Trabajo)."""

from datetime import datetime, timezone
from enum import Enum

from app.extensions import db


class EstadoOrden(str, Enum):
    """Estados de una Orden de Trabajo (RF-07)."""

    PENDIENTE = "pendiente"
    EN_PROGRESO = "en_progreso"
    COMPLETADO = "completado"
    CANCELADO = "cancelado"

    @classmethod
    def values(cls):
        return [e.value for e in cls]


class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    service_id = db.Column(
        db.Integer, db.ForeignKey("services.id"), nullable=False, index=True
    )
    proveedor_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    solicitante_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    estado = db.Column(
        db.Enum(EstadoOrden), nullable=False, default=EstadoOrden.PENDIENTE
    )
    motivo_cancelacion = db.Column(db.String(500), nullable=True)
    creado_en = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    actualizado_en = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    service = db.relationship("Service")
    proveedor = db.relationship("User", foreign_keys=[proveedor_id])
    solicitante = db.relationship("User", foreign_keys=[solicitante_id])
