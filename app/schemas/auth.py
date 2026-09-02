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


class RegisterResponseSchema(Schema):
    """Registro también retorna access/refresh token (Fase 1 RBAC)."""

    id = fields.Integer()
    email = fields.Email()
    rol = fields.String()
    edad_verificada = fields.Boolean()
    acepto_tyc = fields.Boolean()
    fecha_registro = fields.DateTime()
    activo = fields.Boolean()
    profile = fields.Raw()
    access_token = fields.String()
    refresh_token = fields.String()


class ForgotPasswordSchema(Schema):
    """Schema para solicitud de reseteo de contraseña."""
    email = fields.Email(required=True)


class ResetPasswordSchema(Schema):
    """Schema para reseteo de contraseña."""
    token = fields.String(required=True)
    new_password = fields.String(required=True, validate=validate.Length(min=8))
    current_password = fields.String(load_only=True)


class MessageResponseSchema(Schema):
    """Schema para respuestas con mensaje."""
    message = fields.String(required=True)
