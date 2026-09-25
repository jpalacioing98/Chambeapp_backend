"""Marshmallow schemas for Maraña (rebusque) — adenda derivada de una chamba."""

from marshmallow import Schema, fields, validate

from app.models.marana import EstadoMarana


class MaranaCreateSchema(Schema):
    """Body de creación desde una adenda de la chamba (solicitante)."""

    adenda_idx = fields.Integer(required=True)
    titulo = fields.String(required=True, validate=validate.Length(min=3, max=200))
    categoria = fields.String(required=True, validate=validate.Length(min=2, max=120))
    descripcion = fields.String(required=True, validate=validate.Length(min=3, max=4000))
    presupuesto = fields.Integer(required=False, allow_none=True)
    fecha_deseada = fields.Date(required=False, allow_none=True)
    horario = fields.String(required=False, allow_none=True)


class MaranaOfertaCreateSchema(Schema):
    """Body de postulación de un PDS a una maraña."""

    monto = fields.Integer(required=False, allow_none=True)
    mensaje = fields.String(required=False, allow_none=True)


class MaranaOfertaSchema(Schema):
    """Postulación de un PDS."""

    id = fields.Integer()
    marana_id = fields.Integer()
    pds_id = fields.Integer()
    pds_nombre = fields.String(dump_only=True, allow_none=True)
    monto = fields.Integer(allow_none=True)
    mensaje = fields.String(allow_none=True)
    estado = fields.String()
    contra_monto = fields.Integer(allow_none=True)
    contra_mensaje = fields.String(allow_none=True)
    created_at = fields.DateTime()


class MaranaResponderSchema(Schema):
    """Respuesta a una postulación (negociación tipo ofertas)."""

    accion = fields.String(
        required=True,
        validate=validate.OneOf(
            ["aceptar", "rechazar", "contraofertar", "aceptar_contraoferta"]
        ),
    )
    contra_monto = fields.Integer(required=False, allow_none=True)
    contra_mensaje = fields.String(required=False, allow_none=True)


class MaranaEstadoSchema(Schema):
    """Transición de estado de la maraña."""

    accion = fields.String(
        required=True,
        validate=validate.OneOf(["completar", "cancelar"]),
    )


class MaranaPagoSchema(Schema):
    """Check-in de pago directo (como la chamba)."""

    monto_final = fields.Integer(required=False, allow_none=True)


class MaranaSchema(Schema):
    """Detalle completo de una maraña."""

    id = fields.Integer()
    chamba_id = fields.Integer()
    adenda_idx = fields.Integer(allow_none=True)
    solicitante_id = fields.Integer()
    titulo = fields.String()
    categoria = fields.String()
    descripcion = fields.String()
    presupuesto = fields.Integer(allow_none=True)
    ubicacion = fields.String(allow_none=True)
    fecha_deseada = fields.Date(allow_none=True)
    horario = fields.String(allow_none=True)
    estado = fields.Enum(EstadoMarana, by_value=True)
    pago_confirmado_solicitante = fields.Boolean()
    pago_confirmado_prestador = fields.Boolean()
    pago_monto_final = fields.Integer(allow_none=True)
    pds_asignado_id = fields.Integer(allow_none=True)
    fecha_asignacion = fields.DateTime(allow_none=True)
    fecha_entrega = fields.DateTime(allow_none=True)
    fecha_pago = fields.DateTime(allow_none=True)
    creado_en = fields.DateTime()
    actualizado_en = fields.DateTime()
    ofertas = fields.List(
        fields.Nested(MaranaOfertaSchema), dump_only=True, allow_none=True
    )