"""Marshmallow schemas para KYC documental (RF-12 Verificación de Identidad)."""

from marshmallow import Schema, fields, validate


class DocumentoUploadSchema(Schema):
    """Body de POST /documentos (subida/upsert de un documento KYC)."""

    documento_requerido_id = fields.Integer(required=False, allow_none=True)
    clave = fields.String(required=False, allow_none=True)
    archivo_base64 = fields.String(required=False, allow_none=True)
    nombre_archivo = fields.String(required=False, allow_none=True)
    tipo_mime = fields.String(required=False, allow_none=True)
    url = fields.String(required=False, allow_none=True)


class DocumentoVerificarSchema(Schema):
    """Body de POST /documentos/<id>/verificar (decisión del verificador)."""

    decision = fields.String(
        required=True,
        validate=validate.OneOf(["aprobado", "rechazado"]),
    )
    nota = fields.String(required=False, allow_none=True)


class DocumentoRequeridoMinSchema(Schema):
    """Info mínima del catálogo de documentos requeridos."""

    id = fields.Integer()
    clave = fields.String()
    nombre = fields.String()
    obligatorio = fields.Boolean()
    grupo = fields.String(allow_none=True)


class UsuarioMinSchema(Schema):
    """Datos mínimos del usuario propietario del documento."""

    id = fields.Integer()
    nombre = fields.String(allow_none=True)
    email = fields.Email(allow_none=True)
    rol = fields.String(allow_none=True)


class DocumentoUsuarioOutSchema(Schema):
    """Salida de un DocumentoUsuario (con info del requerido anidada)."""

    id = fields.Integer()
    user_id = fields.Integer()
    documento_requerido_id = fields.Integer(allow_none=True)
    documento_clave = fields.String()
    rol = fields.String(allow_none=True)
    estado = fields.String()
    url = fields.String(allow_none=True)
    nombre_archivo = fields.String(allow_none=True)
    tipo_mime = fields.String(allow_none=True)
    nota = fields.String(allow_none=True)
    fecha_envio = fields.DateTime(allow_none=True)
    revisado_en = fields.DateTime(allow_none=True)
    revisor_id = fields.Integer(allow_none=True)
    requerido = fields.Nested(DocumentoRequeridoMinSchema, allow_none=True)


class PendienteOutSchema(Schema):
    """Salida de GET /pendientes (revisión del verificador)."""

    id = fields.Integer()
    user_id = fields.Integer()
    documento_clave = fields.String()
    estado = fields.String()
    url = fields.String(allow_none=True)
    nombre_archivo = fields.String(allow_none=True)
    tipo_mime = fields.String(allow_none=True)
    nota = fields.String(allow_none=True)
    fecha_envio = fields.DateTime(allow_none=True)
    revisado_en = fields.DateTime(allow_none=True)
    revisor_id = fields.Integer(allow_none=True)
    usuario = fields.Nested(UsuarioMinSchema)
    requerido = fields.Nested(DocumentoRequeridoMinSchema)
