"""Marshmallow schemas for provider search (P2-1)."""

from marshmallow import Schema, fields, validate

from app.models.user import RolUsuario


class ProviderSearchSchema(Schema):
    """Query params for provider search."""

    q = fields.String(required=False, load_default=None)
    categoria = fields.String(required=False, load_default=None)
    zona = fields.String(required=False, load_default=None)
    min_rating = fields.Float(required=False, load_default=None)
    verificado = fields.Boolean(required=False, load_default=None)
    page = fields.Integer(required=False, load_default=None)
    per_page = fields.Integer(required=False, load_default=None)


class ProviderSearchItemSchema(Schema):
    """Individual provider in search results."""

    id = fields.Integer()
    email = fields.Email(allow_none=True)
    nombre = fields.String(allow_none=True)
    rol = fields.Enum(RolUsuario, by_value=True)
    habilidades = fields.Raw()
    experiencia = fields.String(allow_none=True)
    zona = fields.String(allow_none=True)
    categorias = fields.Raw()
    portafolio = fields.Raw()
    calificacion_promedio = fields.Float()
    verificado = fields.Boolean()
    badges = fields.Raw()
    perfil_completo = fields.Boolean()


class ProviderSearchResponseSchema(Schema):
    """Paginated response for provider search."""

    items = fields.List(fields.Nested(ProviderSearchItemSchema))
    total = fields.Int()
    page = fields.Int()
    per_page = fields.Int()
    pages = fields.Int()
