"""Marshmallow schemas for contracts (RF-07)."""

from marshmallow import EXCLUDE, Schema, fields, validate

from app.models.contract import EstadoContrato
from app.models.solicitud import EstadoSolicitud


class ContractCreateSchema(Schema):
    """Body de creación de contrato (RF-07.1)."""

    service_id = fields.Integer(required=True)
    proveedor_id = fields.Integer(required=True)


class FirmaSchema(Schema):
    """Datos de la firma de una de las partes del contrato."""

    class Meta:
        # Tolerante a campos extra: la firma es un documento libre y un
        # campo nuevo del cliente no debe romper la transición de estado.
        unknown = EXCLUDE

    nombre = fields.String(required=False, allow_none=True)
    tipo_documento = fields.String(required=False, allow_none=True)
    documento = fields.String(required=False, allow_none=True)
    data_url = fields.String(required=False, allow_none=True)
    fecha = fields.String(required=False, allow_none=True)


class ContractEstadoSchema(Schema):
    """Acción de transición de estado (RF-07.2/3/4)."""

    class Meta:
        unknown = EXCLUDE

    estado = fields.String(
        required=True,
        validate=validate.OneOf(["aceptar", "completar", "confirmar", "cancelar"]),
    )
    motivo_cancelacion = fields.String(required=False, allow_none=True)
    # Firma de la parte que ejecuta la acción 'aceptar' (firma bilateral).
    firma = fields.Nested(FirmaSchema, required=False, allow_none=True)


class SolicitudResumenSchema(Schema):
    """Resumen de la solicitud anidado en el contrato."""

    id = fields.Integer()
    titulo = fields.String()
    categoria = fields.String()
    descripcion = fields.String()
    ubicacion = fields.String()
    presupuesto = fields.Integer(allow_none=True)
    estado = fields.Enum(EstadoSolicitud, by_value=True)


class ContractSchema(Schema):
    id = fields.Integer()
    service_id = fields.Integer()
    proveedor_id = fields.Integer()
    solicitante_id = fields.Integer()
    estado = fields.Enum(EstadoContrato, by_value=True)
    oferta_id = fields.Integer(allow_none=True)
    monto = fields.Float(allow_none=True)
    condiciones = fields.List(fields.Dict(), allow_none=True)
    fecha_deseada = fields.Date(allow_none=True)
    horario = fields.String(allow_none=True)
    firma_solicitante = fields.Boolean()
    firma_proveedor = fields.Boolean()
    firmado_solicitante_en = fields.DateTime(allow_none=True)
    firmado_proveedor_en = fields.DateTime(allow_none=True)
    datos_firma_solicitante = fields.Dict(allow_none=True)
    datos_firma_proveedor = fields.Dict(allow_none=True)
    motivo_cancelacion = fields.String(allow_none=True)
    inicio_en = fields.DateTime(allow_none=True)
    fin_en = fields.DateTime(allow_none=True)
    confirmado_en = fields.DateTime(allow_none=True)  # RF-23
    creado_en = fields.DateTime()
    actualizado_en = fields.DateTime()
    service = fields.Nested(SolicitudResumenSchema, dump_only=True, allow_none=True)


class DisputeCreateSchema(Schema):
    """Body de creación de disputa."""
    reason = fields.String(required=True, validate=validate.Length(min=10, max=2000))
    # Para disputas abiertas durante la negociación (sin contrato).
    oferta_id = fields.Integer(required=False, allow_none=True)


class DisputeDecisionSchema(Schema):
    """Aceptación o rechazo de la decisión propuesta por soporte."""

    accion = fields.String(
        required=True, validate=validate.OneOf(["aceptar", "rechazar"])
    )


class DisputeSchema(Schema):
    """Schema de disputa."""
    id = fields.Integer()
    contract_id = fields.Integer(allow_none=True)
    solicitud_id = fields.Integer(allow_none=True)
    oferta_id = fields.Integer(allow_none=True)
    solicitud_titulo = fields.String(attribute="solicitud.titulo", allow_none=True)
    solicitud_categoria = fields.String(attribute="solicitud.categoria", allow_none=True)
    reason = fields.String()
    status = fields.String()
    chat_habilitado = fields.Boolean()
    chat_habilitado_solicitante = fields.Boolean()
    chat_habilitado_proveedor = fields.Boolean()
    decision_estado = fields.String(allow_none=True)
    decision_solicitante = fields.String(allow_none=True)
    decision_proveedor = fields.String(allow_none=True)
    negociacion_cerrada = fields.Boolean()
    resolved_by = fields.Integer(allow_none=True)
    resolved_at = fields.DateTime(allow_none=True)
    resolution = fields.String(allow_none=True)
    created_at = fields.DateTime()
