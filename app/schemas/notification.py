"""Marshmallow schemas for notifications (RF-16 parcial)."""

from marshmallow import Schema, fields


class NotificationSchema(Schema):
    id = fields.Integer()
    user_id = fields.Integer()
    tipo = fields.String()
    mensaje = fields.String()
    leida = fields.Boolean()
    creado_en = fields.DateTime()
