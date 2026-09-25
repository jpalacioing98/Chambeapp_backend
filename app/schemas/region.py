"""Schemas compartidos de región (división administrativa regional)."""

from marshmallow import Schema, fields


class RegionMinSchema(Schema):
    id = fields.Integer()
    clave = fields.String()
    nombre = fields.String()


class RegionResponseSchema(Schema):
    items = fields.List(fields.Raw())