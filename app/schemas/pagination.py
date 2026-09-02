"""Marshmallow schemas for pagination metadata (P2-4)."""

from marshmallow import Schema, fields


class PaginationSchema(Schema):
    """Metadata de paginación para respuestas paginadas."""

    page = fields.Int(dump_only=True)
    per_page = fields.Int(dump_only=True)
    total = fields.Int(dump_only=True)
    pages = fields.Int(dump_only=True)
