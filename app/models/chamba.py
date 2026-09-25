"""Domain model: Chamba (Módulo de Gestión de Chamba — ciclo de vida de ejecución)."""

from datetime import datetime, timezone
from enum import Enum

from app.extensions import db


class EstadoChamba(str, Enum):
    """Estados de la chamba según el ciclo de vida de ejecución.

    Corresponde a los hitos de `modulo chambas.md`:
    PROGRAMADA (contrato firmado) → EN_PROCESO (inicio de obra) →
    EN_EJECUCION (ejecución/novedades) → PENDIENTE_VALIDACION (solicitud de
    cierre) → LIQUIDACION_CONFIRMADA (pago directo) → FINALIZADA (cierre).
    PAUSADA se usa con el botón de pánico / reporte de incidencias.
    """

    PROGRAMADA = "programada"
    EN_PROCESO = "en_proceso"
    EN_EJECUCION = "en_ejecucion"
    PAUSADA = "pausada"
    PENDIENTE_VALIDACION = "pendiente_validacion"
    LIQUIDACION_CONFIRMADA = "liquidacion_confirmada"
    FINALIZADA = "finalizada"

    @classmethod
    def values(cls):
        return [e.value for e in cls]


class Chamba(db.Model):
    """Chamba: expediente de ejecución de un contrato firmado.

    Relación 1:1 con Contract. Almacena los datos identificables de cada hito
    (evidencias, adendas, novedades, pago directo, calificación).
    """

    __tablename__ = "chambas"

    id = db.Column(db.Integer, primary_key=True)
    contract_id = db.Column(
        db.Integer,
        db.ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    estado = db.Column(
        db.Enum(
            EstadoChamba,
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
        default=EstadoChamba.PROGRAMADA,
    )
    # Estado previo cuando está PAUSADA (para reanudar al estado correcto).
    estado_previo = db.Column(
        db.Enum(
            EstadoChamba,
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=True,
    )

    # Hito 1: activación (contrato firmado)
    fecha_activacion = db.Column(db.DateTime, nullable=True)
    # Hito 2: inicio de obra en sitio
    fecha_inicio_obra = db.Column(db.DateTime, nullable=True)
    # Hito 4: solicitud de cierre y entrega
    fecha_solicitud_cierre = db.Column(db.DateTime, nullable=True)
    # Hito 4: revisión y validación del solicitante (habilidades marcadas en sitio)
    fecha_validacion = db.Column(db.DateTime, nullable=True)
    # Hito 5: liquidación confirmada
    fecha_liquidacion = db.Column(db.DateTime, nullable=True)
    # Hito 6: cierre final
    fecha_finalizacion = db.Column(db.DateTime, nullable=True)

    # Evidencias (URLs de fotos / entorno 360°, MinIO)
    evidencia_entrada = db.Column(db.JSON, nullable=False, default=list)
    evidencia_salida = db.Column(db.JSON, nullable=False, default=list)

    # Adendas al contrato vía chat (hito 3): [{fecha, descripcion, monto_extra, tiempo_extra}]
    adendas = db.Column(db.JSON, nullable=False, default=list)
    # Novedades / incidencias (hito 3): [{fecha, tipo, descripcion}]
    novedades = db.Column(db.JSON, nullable=False, default=list)

    # Hito 5: confirmación de pago directo (check-in de ambas partes)
    pago_confirmado_solicitante = db.Column(db.Boolean, nullable=False, default=False)
    pago_confirmado_prestador = db.Column(db.Boolean, nullable=False, default=False)
    pago_directo_confirmado = db.Column(db.Boolean, nullable=False, default=False)
    pago_monto_final = db.Column(db.Integer, nullable=True)

    # Hito 6: calificación y crecimiento profesional
    rating_estrellas = db.Column(db.Integer, nullable=True)  # 1-5
    rating_comentario = db.Column(db.Text, nullable=True)
    habilidades_validadas = db.Column(db.JSON, nullable=True, default=list)

    creado_en = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    actualizado_en = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    contract = db.relationship("Contract")