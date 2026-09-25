"""Marshmallow schemas for auth/usuarios (validación + OpenAPI)."""

from marshmallow import Schema, fields, validate

from app.models.user import RolUsuario
from app.schemas.region import RegionMinSchema


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
    nombre = fields.String(required=False, load_default=None)
    username = fields.String(required=False, load_default=None)
    telefono = fields.String(required=False, load_default=None)
    consentimiento_datos = fields.Boolean(required=False, load_default=False)
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
    foto_perfil = fields.String(allow_none=True)
    # Datos de cuenta + ubicación (RF-02): viven en User/Profile pero se
    # exponen junto al perfil para que la app los pueda editar.
    nombre = fields.String(attribute="user.nombre", allow_none=True)
    telefono = fields.String(attribute="user.telefono", allow_none=True)
    latitud = fields.Float(allow_none=True)
    longitud = fields.Float(allow_none=True)
    # Campos del User (aditivos) que el frontend necesita en el perfil.
    # Se leen vía la relación Profile.user (dotted attribute).
    nombre = fields.String(attribute="user.nombre", allow_none=True)
    username = fields.String(attribute="user.username", allow_none=True)
    telefono = fields.String(attribute="user.telefono", allow_none=True)
    email_verificado = fields.Boolean(attribute="user.email_verificado", allow_none=True)
    fecha_registro = fields.DateTime(attribute="user.fecha_registro", allow_none=True)


class MeSchema(Schema):
    id = fields.Integer()
    email = fields.Email()
    rol = fields.Enum(RolUsuario, by_value=True)
    nombre = fields.String(allow_none=True)
    username = fields.String(allow_none=True)
    telefono = fields.String(allow_none=True)
    email_verificado = fields.Boolean()
    edad_verificada = fields.Boolean()
    acepto_tyc = fields.Boolean()
    fecha_registro = fields.DateTime()
    activo = fields.Boolean()
    profile = fields.Nested(ProfileSchema)
    region = fields.Nested(RegionMinSchema, allow_none=True)


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


class ChangePasswordSchema(Schema):
    """Cambio de contraseña de un usuario AUTENTICADO (no usa token).

    Valida la contraseña actual y exige la nueva con mínimo 8 caracteres.
    """
    current_password = fields.String(required=True)
    new_password = fields.String(required=True, validate=validate.Length(min=8))


class MessageResponseSchema(Schema):
    """Schema para respuestas con mensaje."""
    message = fields.String(required=True)


class OtpSendSchema(Schema):
    """Schema para envío de OTP."""
    telefono = fields.String(required=True)


class OtpVerifySchema(Schema):
    """Schema para verificación de OTP."""
    telefono = fields.String(required=True)
    code = fields.String(required=True)
