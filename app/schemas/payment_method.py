"""Marshmallow schemas para métodos de pago vinculados (MetodoPago)."""

from marshmallow import Schema, fields, validate


class MetodoPagoCreateSchema(Schema):
    """POST /metodos-pago — vincula una cuenta bancaria.

    El tipo 'billetera' lo crea el sistema automáticamente (primero en la
    lista); los usuarios solo vinculan cuentas bancarias (banco libre +
    número de cuenta).
    """
    tipo = fields.String(validate=validate.OneOf(["banco"]), load_default="banco")
    banco = fields.String(required=True, validate=validate.Length(min=2, max=120))
    numero_cuenta = fields.String(
        required=True, validate=validate.Length(min=4, max=60)
    )


class MetodoPagoSchema(Schema):
    id = fields.Integer()
    tipo = fields.String()
    banco = fields.String(allow_none=True)
    numero_cuenta = fields.String(allow_none=True)
    es_principal = fields.Boolean()
    creado_en = fields.DateTime(allow_none=True)
    # Solo para el método billetera: saldo actual de la wallet del usuario.
    saldo = fields.Float(allow_none=True)


class MessageResponseSchema(Schema):
    message = fields.String(required=True)