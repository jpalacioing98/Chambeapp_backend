"""Marshmallow schemas for payments (RF-08)."""

from marshmallow import Schema, fields, validate

from app.models.payment import EstadoPago


class PaymentCreateSchema(Schema):
    """Body de creacion de pago (RF-08.1)."""

    contract_id = fields.Integer(required=True)
    monto = fields.Integer(required=True, validate=validate.Range(min=1))


class PaymentEstadoSchema(Schema):
    """Accion de reembolso / estado (RF-08.7)."""

    estado = fields.String(
        required=False,
        validate=validate.OneOf(EstadoPago.values()),
    )
    motivo_reembolso = fields.String(required=False, allow_none=True)


class PaymentSchema(Schema):
    id = fields.Integer()
    contract_id = fields.Integer()
    monto = fields.Integer()
    comision = fields.Integer()
    estado = fields.Enum(EstadoPago, by_value=True)
    pasarela = fields.String()
    referencia_pasarela = fields.String(allow_none=True)
    motivo_reembolso = fields.String(allow_none=True)
    creado_en = fields.DateTime()
    actualizado_en = fields.DateTime()
    liberado_en = fields.DateTime(allow_none=True)
