"""Domain models: Maraña (rebusque) — orden menor derivada de una adenda.

Cuando una adenda de una chamba implica trabajo de un perfil distinto al
PDS original, el solicitante puede "lanzarla como maraña": una micro
solicitud publicada a otros PDS. La maraña se paga como la chamba
(check-in dual de pago directo) y su presupuesto SE MUEVE de la adenda.
"""

from datetime import datetime, timezone
from enum import Enum

from app.extensions import db


class EstadoMarana(str, Enum):
    """Estados del ciclo de una maraña."""

    PUBLICADO = "publicado"      # esperando postulaciones de PDS
    ASIGNADO = "asignado"        # oferta aceptada → PDS ejecuta
    COMPLETADO = "completado"    # el PDS entregó el trabajo
    PAGADO = "pagado"            # pago directo confirmado por ambas partes
    CANCELADO = "cancelado"      # sin acuerdo / descartada

    @classmethod
    def values(cls):
        return [e.value for e in cls]


class EstadoMaranaOferta(str, Enum):
    """Estados de la postulación de un PDS a una maraña (como ofertas)."""

    PENDIENTE = "pendiente"
    ACEPTADA = "aceptada"
    RECHAZADA = "rechazada"
    CONTRAOFERTA = "contraoferta"

    @classmethod
    def values(cls):
        return [e.value for e in cls]


class Marana(db.Model):
    __tablename__ = "maranas"

    id = db.Column(db.Integer, primary_key=True)
    # Origen: la chamba y la adenda (índice en chamba.adendas) que la originó.
    chamba_id = db.Column(
        db.Integer, db.ForeignKey("chambas.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    adenda_idx = db.Column(db.Integer, nullable=True)
    solicitante_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )

    titulo = db.Column(db.String(200), nullable=False)
    categoria = db.Column(db.String(120), nullable=False)
    descripcion = db.Column(db.Text, nullable=False)
    presupuesto = db.Column(db.Integer, nullable=True)  # None => "a convenir"
    # Ubicación copiada de la solicitud de la chamba (para el feed del PDS).
    ubicacion = db.Column(db.String(120), nullable=True)
    fecha_deseada = db.Column(db.Date, nullable=True)
    horario = db.Column(db.String(80), nullable=True)

    estado = db.Column(
        db.Enum(
            EstadoMarana,
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
        default=EstadoMarana.PUBLICADO,
    )

    # Pago directo (check-in dual, como la chamba).
    pago_confirmado_solicitante = db.Column(db.Boolean, nullable=False, default=False)
    pago_confirmado_prestador = db.Column(db.Boolean, nullable=False, default=False)
    pago_monto_final = db.Column(db.Integer, nullable=True)

    # PDS asignado (al aceptar una oferta).
    pds_asignado_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True, index=True
    )
    fecha_asignacion = db.Column(db.DateTime, nullable=True)
    fecha_entrega = db.Column(db.DateTime, nullable=True)
    fecha_pago = db.Column(db.DateTime, nullable=True)

    creado_en = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    actualizado_en = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    chamba = db.relationship("Chamba", foreign_keys=[chamba_id])
    solicitante = db.relationship("User", foreign_keys=[solicitante_id])
    pds_asignado = db.relationship("User", foreign_keys=[pds_asignado_id])
    ofertas = db.relationship(
        "MaranaOferta", back_populates="marana", cascade="all, delete-orphan"
    )


class MaranaOferta(db.Model):
    """Postulación de un PDS a una maraña (negociación tipo ofertas)."""

    __tablename__ = "maranas_ofertas"

    id = db.Column(db.Integer, primary_key=True)
    marana_id = db.Column(
        db.Integer, db.ForeignKey("maranas.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    pds_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    monto = db.Column(db.Integer, nullable=True)
    mensaje = db.Column(db.Text, nullable=True)
    estado = db.Column(
        db.String(20), nullable=False, default=EstadoMaranaOferta.PENDIENTE.value
    )
    contra_monto = db.Column(db.Integer, nullable=True)
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

    marana = db.relationship("Marana", back_populates="ofertas")
    pds = db.relationship("User", foreign_keys=[pds_id])