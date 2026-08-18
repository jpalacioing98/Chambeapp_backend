"""Marshmallow schemas for auth/usuarios (validación + OpenAPI)."""

from marshmallow import Schema, fields, validate

from app.models.user import RolUsuario


class RegisterSchema(Schema):
    email = fields.Email(required=True)
    password = fields.String(
        required=True, validate=validate.Length(min=8),
        load_only=True,
    )
    rol = fields.String(
        required=True, validate=validate.OneOf(RolUsuario.values())
    )
    acepto_tyc = fields.Boolean(required=True)
    ip = fields.String(required=False, load_default=None)


class LoginSchema(Schema):
    email = fields.Email(required=True)
    password = fields.String(required=True, load_only=True)


class RefreshSchema(Schema):
    # Cuerpo vacío; el refresh_token va en la cookie/header JWT.
    pass


class ProfileSchema(Schema):
    habilidades = fields.Raw()
    experiencia = fields.String(allow_none=True)
    zona = fields.String(allow_none=True)
    categorias = fields.Raw()
    portafolio = fields.Raw()
    calificacion_promedio = fields.Float()
    verificado = fields.Boolean()
    badges = fields.Raw()
    perfil_completo = fields.Boolean()


class MeSchema(Schema):
    id = fields.Integer()
    email = fields.Email()
    rol = fields.Enum(RolUsuario, by_value=True)
    edad_verificada = fields.Boolean()
    acepto_tyc = fields.Boolean()
    fecha_registro = fields.DateTime()
    activo = fields.Boolean()
    profile = fields.Nested(ProfileSchema)
