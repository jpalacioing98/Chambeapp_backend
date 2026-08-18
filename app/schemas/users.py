"""Marshmallow schemas for perfiles de usuario (RF-02, RF-03.4)."""

from marshmallow import Schema, fields

from app.models.user import RolUsuario


class ProfileUpdateSchema(Schema):
    habilidades = fields.Raw(required=False, allow_none=True)
    experiencia = fields.String(required=False, allow_none=True)
    zona = fields.String(required=False, allow_none=True)
    categorias = fields.Raw(required=False, allow_none=True)
    portafolio = fields.Raw(required=False, allow_none=True)


class PublicProfileSchema(Schema):
    id = fields.Integer()
    email = fields.Email(allow_none=True)
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
    ratings_recientes = fields.List(fields.Nested("RatingSchema"), allow_none=True)
    sin_calificaciones = fields.Boolean(allow_none=True)
