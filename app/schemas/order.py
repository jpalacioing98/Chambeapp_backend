"""Marshmallow schemas for orders (RF-07)."""

from marshmallow import Schema, fields, validate

from app.models.order import EstadoOrden
from app.models.solicitud import EstadoSolicitud


class OrderCreateSchema(Schema):
    """Body de creación de orden (RF-07.1)."""

    service_id = fields.Integer(required=True)
    proveedor_id = fields.Integer(required=True)


class OrderEstadoSchema(Schema):
    """Acción de transición de estado (RF-07.2/3/4)."""

    estado = fields.String(
        required=True,
        validate=validate.OneOf(["aceptar", "completar", "cancelar"]),
    )
    motivo_cancelacion = fields.String(required=False, allow_none=True)


class SolicitudResumenSchema(Schema):
    """Resumen de la solicitud anidado en la orden."""

    id = fields.Integer()
    categoria = fields.String()
    descripcion = fields.String()
    ubicacion = fields.String()
    estado = fields.Enum(EstadoSolicitud, by_value=True)


class OrderSchema(Schema):
    id = fields.Integer()
    service_id = fields.Integer()
    proveedor_id = fields.Integer()
    solicitante_id = fields.Integer()
    estado = fields.Enum(EstadoOrden, by_value=True)
    motivo_cancelacion = fields.String(allow_none=True)
    creado_en = fields.DateTime()
    actualizado_en = fields.DateTime()
    service = fields.Nested(SolicitudResumenSchema, dump_only=True, allow_none=True)
