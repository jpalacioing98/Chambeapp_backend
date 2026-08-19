"""Marshmallow schemas for Ofertas (negociación pds/solicitante)."""

from marshmallow import Schema, fields, validate

from app.models.oferta import EstadoOferta


class OfertaSchema(Schema):
    """Serializa una oferta (incluye nombre del pds)."""

    id = fields.Integer()
    solicitud_id = fields.Integer()
    pds_id = fields.Integer()
    pds_nombre = fields.String(dump_only=True, allow_none=True)
    monto = fields.Float(allow_none=True)
    mensaje = fields.String(allow_none=True)
    estado = fields.String()
    contra_monto = fields.Float(allow_none=True)
    contra_mensaje = fields.String(allow_none=True)
    created_at = fields.DateTime()


class OfertaCreateSchema(Schema):
    """Body de creación de oferta (monto/mensaje opcionales)."""

    monto = fields.Float(required=False, allow_none=True)
    mensaje = fields.String(required=False, allow_none=True)


class OfertaResponderSchema(Schema):
    """Body de respuesta a una oferta."""

    accion = fields.String(
        required=True,
        validate=validate.OneOf(
            [
                "aceptar",
                "rechazar",
                "contraofertar",
                "aceptar_contraoferta",
            ]
        ),
    )
    contra_monto = fields.Float(required=False, allow_none=True)
    contra_mensaje = fields.String(required=False, allow_none=True)


class MisOfertasSchema(Schema):
    """Oferta del pds con resumen de su solicitud."""

    id = fields.Integer()
    solicitud_id = fields.Integer()
    monto = fields.Float(allow_none=True)
    mensaje = fields.String(allow_none=True)
    estado = fields.String()
    contra_monto = fields.Float(allow_none=True)
    contra_mensaje = fields.String(allow_none=True)
    created_at = fields.DateTime()
    solicitud = fields.Dict(allow_none=True)
