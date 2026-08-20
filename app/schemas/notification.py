"""Marshmallow schemas for notifications (RF-10)."""

from marshmallow import Schema, fields


class NotificationSchema(Schema):
    id = fields.Integer()
    user_id = fields.Integer()
    tipo = fields.String()
    titulo = fields.String(allow_none=True)
    mensaje = fields.String()
    datos = fields.Raw(allow_none=True)
    leida = fields.Boolean()
    creado_en = fields.DateTime()
