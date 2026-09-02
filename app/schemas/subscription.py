"""Marshmallow schemas for Suscripciones (RF-11)."""

from marshmallow import Schema, fields, validate


class SuscripcionSchema(Schema):
    """Serializa una suscripción."""

    id = fields.Integer()
    user_id = fields.Integer()
    plan = fields.String()
    estado = fields.String()
    inicio_en = fields.DateTime()
    fin_en = fields.DateTime(allow_none=True)
    monto = fields.Integer()
    metodo_pago = fields.String()
    creado_en = fields.DateTime()
    actualizado_en = fields.DateTime()


class SuscripcionCreateSchema(Schema):
    """Body de creación de suscripción."""

    plan = fields.String(
        required=True,
        validate=validate.OneOf(["basico", "profesional"]),
    )


class PlanSchema(Schema):
    """Catálogo de planes (hardcoded)."""

    plan = fields.String()
    nombre = fields.String()
    precio = fields.Integer()
    beneficios = fields.List(fields.String())
