"""Marshmallow schemas for Anuncios Laborales (ofertas no vinculantes)."""

from marshmallow import Schema, fields, validate

from app.models.anuncio import EstadoAnuncio, EstadoPostulacionAnuncio


class AnuncioCreateSchema(Schema):
    """Body de creación de un anuncio laboral (negocio)."""

    titulo = fields.String(required=True, validate=validate.Length(min=3, max=200))
    descripcion = fields.String(required=True, validate=validate.Length(min=3, max=4000))
    categoria = fields.String(required=True, validate=validate.Length(min=2, max=120))
    ubicacion = fields.String(required=False, allow_none=True, validate=validate.Length(max=160))
    latitud = fields.Float(required=False, allow_none=True)
    longitud = fields.Float(required=False, allow_none=True)
    vacantes = fields.Integer(required=False, allow_none=True, validate=validate.Range(min=1))


class AnuncioEstadoSchema(Schema):
    """cerrar / abrir un anuncio."""

    accion = fields.String(
        required=True,
        validate=validate.OneOf(["cerrar", "abrir"]),
    )


class AnuncioPostulacionCreateSchema(Schema):
    """Body de postulación de un PDS (contacto para el negocio)."""

    mensaje = fields.String(required=False, allow_none=True, validate=validate.Length(max=2000))
    telefono_contacto = fields.String(required=False, allow_none=True, validate=validate.Length(max=40))
    email_contacto = fields.String(required=False, allow_none=True, validate=validate.Email())


class AnuncioPostulacionSchema(Schema):
    """Postulación con datos de contacto (gestión del negocio)."""

    id = fields.Integer()
    anuncio_id = fields.Integer()
    pds_id = fields.Integer()
    pds_nombre = fields.String(dump_only=True, allow_none=True)
    mensaje = fields.String(allow_none=True)
    telefono_contacto = fields.String(allow_none=True)
    email_contacto = fields.String(allow_none=True)
    estado = fields.Enum(EstadoPostulacionAnuncio, by_value=True)
    created_at = fields.DateTime()


class PostulacionEstadoSchema(Schema):
    """Gestión de contacto: contactar / descartar."""

    accion = fields.String(
        required=True,
        validate=validate.OneOf(["contactar", "descartar"]),
    )


class AnuncioSchema(Schema):
    """Detalle del anuncio laboral."""

    id = fields.Integer()
    negocio_id = fields.Integer()
    negocio_nombre = fields.String(dump_only=True, allow_none=True)
    titulo = fields.String()
    descripcion = fields.String()
    categoria = fields.String()
    ubicacion = fields.String(allow_none=True)
    latitud = fields.Float(allow_none=True)
    longitud = fields.Float(allow_none=True)
    vacantes = fields.Integer(allow_none=True)
    estado = fields.Enum(EstadoAnuncio, by_value=True)
    creado_en = fields.DateTime()
    actualizado_en = fields.DateTime()
    # Solo se incluye para el dueño (dump dinámico por contexto).
    postulaciones = fields.List(
        fields.Nested(AnuncioPostulacionSchema), dump_only=True, allow_none=True
    )
    postulaciones_count = fields.Integer(dump_only=True, dump_default=0)