"""Marshmallow schemas for services (RF-04)."""

from marshmallow import Schema, fields

from app.models.service import EstadoServicio


class ServiceCreateSchema(Schema):
    """Body de creación. Validación estricta (400) se hace en la ruta."""

    categoria = fields.String(required=False, allow_none=True)
    descripcion = fields.String(required=False, allow_none=True)
    ubicacion = fields.String(required=False, allow_none=True)
    presupuesto = fields.Integer(required=False, allow_none=True)
    especificaciones_tecnicas = fields.Raw(required=False, allow_none=True)


class ServiceEstadoSchema(Schema):
    estado = fields.String(
        required=True, validate=fields.validate.OneOf(EstadoServicio.values())
    )


class ServiceSchema(Schema):
    id = fields.Integer()
    solicitante_id = fields.Integer()
    categoria = fields.String()
    descripcion = fields.String()
    ubicacion = fields.String()
    presupuesto = fields.Integer(allow_none=True)
    estado = fields.Enum(EstadoServicio, by_value=True)
    especificaciones_tecnicas = fields.Raw(allow_none=True)
    creado_en = fields.DateTime()
    actualizado_en = fields.DateTime()
    advertencia = fields.String(dump_only=True, allow_none=True)
    ratings = fields.List(fields.Nested("RatingSchema"), dump_only=True, allow_none=True)
