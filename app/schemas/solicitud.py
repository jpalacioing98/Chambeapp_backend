"""Marshmallow schemas for solicitudes (RF-04)."""

from marshmallow import Schema, fields

from app.models.solicitud import EstadoSolicitud, UrgenciaSolicitud


class SolicitudCreateSchema(Schema):
    """Body de creación. Validación estricta (400) se hace en la ruta."""

    titulo = fields.String(required=True)
    categoria = fields.String(required=False, allow_none=True)
    descripcion = fields.String(required=False, allow_none=True)
    ubicacion = fields.String(required=False, allow_none=True)
    presupuesto = fields.Integer(required=False, allow_none=True)
    fecha_deseada = fields.Date(required=False, allow_none=True)
    urgencia = fields.String(
        required=False,
        allow_none=True,
        validate=fields.validate.OneOf(UrgenciaSolicitud.values()),
    )
    especificaciones_tecnicas = fields.Raw(required=False, allow_none=True)


class SolicitudEstadoSchema(Schema):
    estado = fields.String(
        required=True, validate=fields.validate.OneOf(EstadoSolicitud.values())
    )


class SolicitudSchema(Schema):
    id = fields.Integer()
    solicitante_id = fields.Integer()
    categoria = fields.String()
    descripcion = fields.String()
    ubicacion = fields.String()
    presupuesto = fields.Integer(allow_none=True)
    titulo = fields.String()
    fecha_deseada = fields.Date(allow_none=True)
    urgencia = fields.String(allow_none=True)
    estado = fields.Enum(EstadoSolicitud, by_value=True)
    especificaciones_tecnicas = fields.Raw(allow_none=True)
    creado_en = fields.DateTime()
    actualizado_en = fields.DateTime()
    advertencia = fields.String(dump_only=True, allow_none=True)
    ratings = fields.List(fields.Nested("RatingSchema"), dump_only=True, allow_none=True)
