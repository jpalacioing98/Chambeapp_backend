"""Marshmallow schemas for ratings (RF-03)."""

from marshmallow import Schema, fields, validate


class RatingCreateSchema(Schema):
    puntaje = fields.Integer(
        required=True, validate=validate.Range(min=1, max=5)
    )
    comentario = fields.String(required=False, allow_none=True)
    calificado_id = fields.Integer(required=True)


class RatingSchema(Schema):
    id = fields.Integer()
    service_id = fields.Integer()
    autor_id = fields.Integer()
    calificado_id = fields.Integer()
    puntaje = fields.Integer()
    comentario = fields.String(allow_none=True)
    reportado = fields.Boolean()
    creado_en = fields.DateTime()
