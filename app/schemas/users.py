"""Marshmallow schemas for perfiles de usuario (RF-02, RF-03.4)."""

from marshmallow import Schema, fields

from app.models.user import RolUsuario


class ProfileUpdateSchema(Schema):
    habilidades = fields.Raw(required=False, allow_none=True)
    experiencia = fields.String(required=False, allow_none=True)
    zona = fields.String(required=False, allow_none=True)
    categorias = fields.Raw(required=False, allow_none=True)
    portafolio = fields.Raw(required=False, allow_none=True)
    # Campos del User y de ubicación (RF-02 edición de perfil):
    nombre = fields.String(required=False, allow_none=True)
    telefono = fields.String(required=False, allow_none=True)
    latitud = fields.Float(required=False, allow_none=True)
    longitud = fields.Float(required=False, allow_none=True)


class FotoPerfilSchema(Schema):
    """Body de POST /users/me/foto-perfil (subida base64 MVP)."""
    archivo_base64 = fields.String(required=True)
    nombre_archivo = fields.String(required=False, allow_none=True)
    tipo_mime = fields.String(required=False, allow_none=True)


class FotoPerfilResponseSchema(Schema):
    foto_perfil = fields.String(allow_none=True)
    message = fields.String(allow_none=True)


class PublicProfileSchema(Schema):
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
    foto_perfil = fields.String(allow_none=True)
    # Habilidades con su ruta de niveles + cuáles certificó el usuario.
    habilidades_detalle = fields.Raw(allow_none=True)
    certificaciones = fields.Raw(allow_none=True)
    ratings_recientes = fields.List(fields.Nested("RatingSchema"), allow_none=True)
    sin_calificaciones = fields.Boolean(allow_none=True)
