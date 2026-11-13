"""Domain models: Contract (RF-07 — Gestión Contractual y Órdenes de Trabajo)."""

from datetime import datetime, timezone
from enum import Enum

from app.extensions import db


class EstadoContrato(str, Enum):
    """Estados de un Contrato de Trabajo (RF-07)."""

    PENDIENTE = "pendiente"
    EN_PROGRESO = "en_progreso"
    COMPLETADO_PENDIENTE = "completado_pendiente"  # RF-23: PDS marcó completado, esperando confirmación
    COMPLETADO = "completado"
    CANCELADO = "cancelado"
    # RBAC Fase 2: moderación admin (flag de contrato sospechoso).
    MARCADO = "marcado"

    @classmethod
    def values(cls):
        return [e.value for e in cls]


class Contract(db.Model):
    __tablename__ = "contracts"
    __table_args__ = (
        db.Index("ix_contracts_proveedor_creado", "proveedor_id", "creado_en"),
        db.Index(
            "ix_contracts_solicitante_creado", "solicitante_id", "creado_en"
        ),
        db.Index("ix_contracts_estado_creado", "estado", "creado_en"),
    )

    id = db.Column(db.Integer, primary_key=True)
    service_id = db.Column(
        db.Integer, db.ForeignKey("solicitudes.id"), nullable=False, index=True
    )
    proveedor_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )
    solicitante_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )
    estado = db.Column(
        db.Enum(EstadoContrato), nullable=False, default=EstadoContrato.PENDIENTE
    )
    # Oferta que originó el contrato (la negociación bilateral que lo dejó
    # sin efecto). Sin FK para no atar el contrato a la fila de oferta.
    oferta_id = db.Column(db.Integer, nullable=True, index=True)
    # Valor final acordado: el monto de la oferta o contraoferta aceptada
    # por ambas partes. Es la fuente de verdad del contrato (la solicitud
    # se actualiza con el mismo valor).
    monto = db.Column(db.Float, nullable=True)
    # Condiciones de la negociación que forman parte integral del contrato.
    condiciones = db.Column(db.JSON, nullable=True)
    # Parámetros "a convenir" concretados en la negociación.
    fecha_deseada = db.Column(db.Date, nullable=True)
    horario = db.Column(db.String(80), nullable=True)
    # Firmas bilaterales y paralelas: cada parte firma cuando quiere, sin
    # esperar a la otra. El contrato se activa cuando ambos han firmado.
    firma_solicitante = db.Column(db.Boolean, nullable=False, default=False)
    firma_proveedor = db.Column(db.Boolean, nullable=False, default=False)
    firmado_solicitante_en = db.Column(db.DateTime, nullable=True)
    firmado_proveedor_en = db.Column(db.DateTime, nullable=True)
    datos_firma_solicitante = db.Column(db.JSON, nullable=True)
    datos_firma_proveedor = db.Column(db.JSON, nullable=True)
    motivo_cancelacion = db.Column(db.String(500), nullable=True)
    # Ciclo de vida "capeta": check-in (inicio) / check-out (fin) del pds.
    inicio_en = db.Column(db.DateTime, nullable=True)
    fin_en = db.Column(db.DateTime, nullable=True)
    confirmado_en = db.Column(db.DateTime, nullable=True)  # RF-23: Confirmación dual
    creado_en = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    actualizado_en = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    service = db.relationship("Solicitud")
    proveedor = db.relationship("User", foreign_keys=[proveedor_id])
    solicitante = db.relationship("User", foreign_keys=[solicitante_id])


class Dispute(db.Model):
    """Disputa / escalamiento de contrato (RBAC Fase 2).

    La resolución es solo informativa: la plataforma no retiene ni congela
    fondos, por lo que no aplica una acción de pago.
    """

    __tablename__ = "disputes"
    __table_args__ = (
        db.Index("ix_disputes_contract_creado", "contract_id", "created_at"),
        db.Index("ix_disputes_solicitud_creado", "solicitud_id", "created_at"),
        db.Index("ix_disputes_status_creado", "status", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    # Una disputa puede existir antes del contrato (negociación en curso).
    # En ese caso queda ligada a la solicitud/oferta y contract_id es NULL.
    contract_id = db.Column(
        db.Integer, db.ForeignKey("contracts.id"), nullable=True
    )
    solicitud_id = db.Column(
        db.Integer, db.ForeignKey("solicitudes.id"), nullable=True
    )
    oferta_id = db.Column(db.Integer, nullable=True)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(
        db.String(20), default="abierta", nullable=False
    )  # abierta | resuelta
    resolved_by = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True
    )
    resolved_at = db.Column(db.DateTime, nullable=True)
    resolution = db.Column(db.Text, nullable=True)
    # Mientras la disputa está abierta, el chat entre las partes queda
    # bloqueado hasta que soporte lo habilite. Soporte puede habilitarlo
    # para una parte o para ambas.
    chat_habilitado = db.Column(db.Boolean, nullable=False, default=False)
    chat_habilitado_solicitante = db.Column(
        db.Boolean, nullable=False, default=False
    )
    chat_habilitado_proveedor = db.Column(
        db.Boolean, nullable=False, default=False
    )
    # Decisión de soporte sobre las variables de la disputa:
    # pendiente | aceptada | rechazada.
    decision_estado = db.Column(db.String(20), nullable=True)
    decision_solicitante = db.Column(db.String(20), nullable=True)
    decision_proveedor = db.Column(db.String(20), nullable=True)
    decision_message_id = db.Column(db.Integer, nullable=True)
    negociacion_cerrada = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    contract = db.relationship("Contract")
    solicitud = db.relationship("Solicitud")
